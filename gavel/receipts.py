"""Append-only receipts: one JSON line per judgment, offline-verifiable."""

import hashlib
import json
from datetime import datetime, timezone

RECEIPT_VERSION = 1


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def make_receipt(case_id: str, arm: str, pin: dict, prompt_sha: str, anchor_sha: str,
                 raw_response: str, verdict: dict | None, unaudited_reason: str | None) -> dict:
    core = {
        "case_id": case_id,
        "arm": arm,
        "pin_sha256": _hash(pin),
    }
    return {
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


def verify_file(path) -> list[dict]:
    """Structural verification. Full replay (re-running the judge) is opt-in."""
    return load_receipts(path)
