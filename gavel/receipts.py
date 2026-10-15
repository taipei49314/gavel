"""Append-only receipts: one JSON line per judgment, offline-verifiable.

Content verification (round-2 contract): receipts that embed their full
prompt/anchor text and execution settings can be re-hashed and their raw
response re-parsed; a receipt whose recomputed hashes or re-parsed verdict
disagree with its stored fields fails verification. Legacy receipts
(round-0/1) carry no embedded content and only get structural checks.
Replay (re-running the model) is a separate, explicit feature.
"""

import hashlib
import json
from datetime import datetime, timezone

RECEIPT_VERSION = 2


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def make_receipt(case_id: str, arm: str, pin: dict, prompt_sha: str, anchor_sha: str,
                 raw_response: str, verdict: dict | None, unaudited_reason: str | None,
                 prompt_text: str | None = None, anchor_text: str | None = None,
                 execution: dict | None = None) -> dict:
    core = {
        "case_id": case_id,
        "arm": arm,
        "pin_sha256": _hash(pin),
    }
    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "receipt_id": _hash(core)[:16],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_id": case_id,
        "arm": arm,
        "pin": pin,
        "pin_sha256": core["pin_sha256"],
        "prompt_sha256": prompt_sha,
        "anchor_sha256": anchor_sha,
        "raw_response": raw_response,
        "verdict": verdict,
        "unaudited_reason": unaudited_reason,
    }
    if prompt_text is not None:
        receipt["prompt_text"] = prompt_text
    if anchor_text is not None:
        receipt["anchor_text"] = anchor_text
    if execution is not None:
        receipt["execution"] = execution
    return receipt


def write_receipt(path, receipt: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(receipt, sort_keys=True) + "\n")


REQUIRED_FIELDS = {
    "receipt_version", "receipt_id", "timestamp", "case_id", "arm", "pin",
    "pin_sha256", "prompt_sha256", "anchor_sha256", "raw_response",
    "verdict", "unaudited_reason",
}


def load_receipts(path) -> list[dict]:
    receipts = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: not JSON: {exc}") from exc
            missing = REQUIRED_FIELDS - set(rec.keys())
            if missing:
                raise ValueError(f"{path}:{lineno}: missing fields {sorted(missing)}")
            if _hash({"case_id": rec["case_id"], "arm": rec["arm"],
                      "pin_sha256": rec["pin_sha256"]})[:16] != rec["receipt_id"]:
                raise ValueError(f"{path}:{lineno}: receipt_id mismatch")
            receipts.append(rec)
    return receipts


def verify_content(rec: dict, mechanism_classes: list[str]) -> None:
    """Content verification for one receipt (v2+). Raises ValueError on any
    disagreement between embedded content, recomputed hashes, and the
    stored verdict. This never calls a model — replay is separate."""
    from .judge import extract_json_v2, validate_verdict

    if rec.get("prompt_text") is None or rec.get("anchor_text") is None:
        return  # legacy receipt: structural checks only
    if hashlib.sha256(rec["prompt_text"].encode()).hexdigest() != rec["prompt_sha256"]:
        raise ValueError(f"{rec['case_id']}/{rec['arm']}: prompt hash mismatch")
    if hashlib.sha256(rec["anchor_text"].encode()).hexdigest() != rec["anchor_sha256"]:
        raise ValueError(f"{rec['case_id']}/{rec['arm']}: anchor hash mismatch")
    if rec["unaudited_reason"]:
        if rec["verdict"] is not None or rec["raw_response"] is not None:
            raise ValueError(f"{rec['case_id']}/{rec['arm']}: unaudited receipt carries verdict/raw")
        return
    try:
        reparsed = validate_verdict(extract_json_v2(rec["raw_response"]), mechanism_classes)
    except Exception as exc:
        raise ValueError(f"{rec['case_id']}/{rec['arm']}: raw response no longer parses: {exc}")
    if reparsed != rec["verdict"]:
        raise ValueError(f"{rec['case_id']}/{rec['arm']}: re-parsed verdict differs from stored")


def verify_file(path, mechanism_classes=None, content: bool = False) -> list[dict]:
    """Structural verification; optional content verification per receipt."""
    receipts = load_receipts(path)
    if content:
        for rec in receipts:
            verify_content(rec, mechanism_classes)
    return receipts
