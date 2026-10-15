"""Append-only receipts: one JSON line per judgment attempt, offline-verifiable.

Receipt v3 (takeover audit 2026-10-15: CR-06, CR-07, R2-12, GOV-12):
- receipt_id is the sha256 of the canonical JSON of the whole receipt body
  (every field except receipt_id itself). run, attempt, timestamp, host,
  transport and its version, options, pins, texts, raw output, verdict and
  execution settings are all bound by it.
- prev_receipt_sha256 is the receipt_id of the preceding receipt in the same
  file (GENESIS for the first). A deleted, inserted or reordered line breaks
  the chain. A truncated tail is caught when the caller supplies the
  expected head or count (run_paper records both in results.json).
- A file holds receipts of one version only, so a v3 file holds only v3
  receipts. A v2 receipt must embed its prompt and anchor text, and a v1/v2
  receipt carrying v3-only fields is rejected. Those close the downgrade
  paths from v3 to an older, weaker rule set.
- pin_sha256 is recomputed from pin for every version.
- An UNAUDITED v3 receipt keeps the raw model output when there was any
  (CR-07); it never carries a verdict.
- The host (socket.gethostname, platform.node), the Ollama version, the
  model digest read before and after the call, the options (temperature,
  num_ctx, seed if any) and the transport are recorded (GOV-12).

Older receipts keep the rules they were written under: v1 (round-0, round-1,
attack round-1) get structural checks only; v2 (round-2) get structural
checks and, with content=True, re-hashing of the embedded texts and a
re-parse of the raw output with the round-2 extractor (extract_json_v2).

The hashes are unkeyed. Verification detects accidental and naive edits,
deletions, reordering and downgrades; it cannot detect a whole file rewritten
by someone who recomputes every hash. The external anchors against that are
git history and the head recorded in results.json.
Replay (re-running the model to reproduce a verdict) is not implemented;
verification here never calls a model.
"""

import hashlib
import json
import platform
import socket
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from . import __version__
from .anchor import ANCHOR_VERSION, parse_anchor
from .judge import (OLLAMA, SCHEMA_VERSION, extract_json, extract_json_v2,
                    validate_verdict)
from .prompt import MECHANISM_CLASSES, PROMPT_VERSION, render_prompt

RECEIPT_VERSION = 3
GENESIS = "0" * 64

# v1/v2 structure (unchanged from round-0..2).
REQUIRED_FIELDS = {
    "receipt_version", "receipt_id", "timestamp", "case_id", "arm", "pin",
    "pin_sha256", "prompt_sha256", "anchor_sha256", "raw_response",
    "verdict", "unaudited_reason",
}
V2_CONTENT_FIELDS = ("prompt_text", "anchor_text")

V3_FIELDS = frozenset({
    "receipt_version", "receipt_id", "prev_receipt_sha256", "harness_version",
    "paper_id", "case_id", "case_sha256", "arm", "run", "attempt",
    "timestamp", "host", "transport", "pin", "pin_sha256", "pin_after",
    "options", "prompt_version", "anchor_version", "schema_version",
    "prompt_sha256", "anchor_sha256", "prompt_text", "anchor_text",
    "raw_response", "verdict", "unaudited_reason", "generation", "execution",
})
# Fields no v1/v2 receipt ever carried; their presence on an older receipt
# means a v3 receipt was relabelled.
V3_ONLY_FIELDS = V3_FIELDS - REQUIRED_FIELDS - {"prompt_text", "anchor_text",
                                                "execution", "run"}


def _hash(obj) -> str:
    """Legacy hash (v1/v2 receipt_id and pin_sha256 for every version)."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def canonical_json(obj) -> bytes:
    """The canonical byte form hashed into a v3 receipt_id."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def receipt_digest(receipt: dict) -> str:
    """sha256 over the canonical JSON of every field except receipt_id."""
    body = {k: v for k, v in receipt.items() if k != "receipt_id"}
    return hashlib.sha256(canonical_json(body)).hexdigest()


@lru_cache(maxsize=1)
def _host_facts() -> tuple:
    return (("hostname", socket.gethostname()), ("node", platform.node()),
            ("system", platform.system()), ("python", platform.python_version()))


def host_facts() -> dict:
    """Where this process runs. Recorded in every v3 receipt (GOV-12)."""
    return dict(_host_facts())


def _is_pos_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 \
        and all(c in "0123456789abcdef" for c in value)


def build_receipt(*, case_id: str, arm: str, run: int, attempt: int, judgment: dict,
                  paper_id: str | None = None, case_sha256: str | None = None,
                  timestamp: str | None = None, host: dict | None = None) -> dict:
    """The unsealed v3 body for one judgment attempt.

    judgment is a gavel.qualify.judge_case() result. paper_id and case_sha256
    come from the locked paper manifest (None for an ad-hoc scan).
    ReceiptLog.append() seals it (prev_receipt_sha256, receipt_id).
    """
    for name, value in (("run", run), ("attempt", attempt)):
        if not _is_pos_int(value):
            raise ValueError(f"{name} must be an integer >= 1, got {value!r}")
    pin = judgment["pin"]
    return {
        "receipt_version": RECEIPT_VERSION,
        "harness_version": __version__,
        "paper_id": paper_id,
        "case_id": case_id,
        "case_sha256": case_sha256,
        "arm": arm,
        "run": run,
        "attempt": attempt,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": dict(host) if host is not None else host_facts(),
        "transport": dict(judgment["transport"]),
        "pin": pin,
        "pin_sha256": _hash(pin),
        "pin_after": judgment.get("pin_after"),
        "options": dict(judgment.get("options") or {}),
        "prompt_version": judgment["prompt_version"],
        "anchor_version": judgment["anchor_version"],
        "schema_version": judgment["schema_version"],
        "prompt_sha256": judgment["prompt_sha256"],
        "anchor_sha256": judgment["anchor_sha256"],
        "prompt_text": judgment["prompt_text"],
        "anchor_text": judgment["anchor_text"],
        "raw_response": judgment["raw"],
        "verdict": judgment["verdict"],
        "unaudited_reason": judgment["unaudited"],
        "generation": dict(judgment.get("generation") or {}),
        "execution": dict(judgment.get("execution") or {}),
    }


def seal_receipt(body: dict, prev_receipt_sha256: str) -> dict:
    """Attach the chain link and the full-body receipt_id."""
    receipt = {k: v for k, v in body.items()
               if k not in ("receipt_id", "prev_receipt_sha256")}
    receipt["prev_receipt_sha256"] = prev_receipt_sha256
    receipt["receipt_id"] = receipt_digest(receipt)
    return receipt


class ReceiptLog:
    """An append-only, hash-chained v3 receipts file.

    Opening verifies the existing file's structure and chain and refuses a
    file holding v1/v2 receipts (a file holds one version).
    """

    def __init__(self, path):
        self.path = Path(path)
        existing = load_receipts(self.path) if self.path.exists() else []
        if existing and existing[0]["receipt_version"] != RECEIPT_VERSION:
            raise ValueError(f"{self.path.name}: holds v{existing[0]['receipt_version']} "
                             f"receipts; v{RECEIPT_VERSION} receipts go to a new file")
        self.head = existing[-1]["receipt_id"] if existing else GENESIS
        self.count = len(existing)

    def append(self, body: dict) -> dict:
        receipt = seal_receipt(body, self.head)
        line = json.dumps(receipt, sort_keys=True) + "\n"
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
        self.head = receipt["receipt_id"]
        self.count += 1
        return receipt


def append_receipt(path, body: dict) -> dict:
    """Seal body onto the chain of the receipts file at path and append it."""
    return ReceiptLog(path).append(body)


def _check_legacy_structure(rec: dict, where: str, version: int) -> None:
    missing = REQUIRED_FIELDS - set(rec.keys())
    if missing:
        raise ValueError(f"{where}: missing fields {sorted(missing)}")
    v3_only = V3_ONLY_FIELDS & set(rec.keys())
    if v3_only:
        raise ValueError(f"{where}: v{version} receipt carries v3 fields "
                         f"{sorted(v3_only)} (downgraded receipt)")
    if _hash(rec["pin"]) != rec["pin_sha256"]:
        raise ValueError(f"{where}: pin_sha256 does not match pin")
    if _hash({"case_id": rec["case_id"], "arm": rec["arm"],
              "pin_sha256": rec["pin_sha256"]})[:16] != rec["receipt_id"]:
        raise ValueError(f"{where}: receipt_id mismatch")
    if version == 2:
        for key in V2_CONTENT_FIELDS:
            if not isinstance(rec.get(key), str):
                raise ValueError(f"{where}: v2 receipt lacks embedded {key} "
                                 f"(content stripped)")


def _check_v3_structure(rec: dict, where: str) -> None:
    missing = V3_FIELDS - set(rec.keys())
    if missing:
        raise ValueError(f"{where}: missing fields {sorted(missing)}")
    unknown = set(rec.keys()) - V3_FIELDS
    if unknown:
        raise ValueError(f"{where}: unknown fields {sorted(unknown)}")
    try:
        digest = receipt_digest(rec)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{where}: receipt body is not canonical JSON: {exc}") from exc
    if digest != rec["receipt_id"]:
        raise ValueError(f"{where}: receipt_id mismatch (receipt body changed)")
    if _hash(rec["pin"]) != rec["pin_sha256"]:
        raise ValueError(f"{where}: pin_sha256 does not match pin")
    if not _is_hex64(rec["prev_receipt_sha256"]):
        raise ValueError(f"{where}: prev_receipt_sha256 is not a sha256")
    for name in ("run", "attempt"):
        if not _is_pos_int(rec[name]):
            raise ValueError(f"{where}: {name} must be an integer >= 1")
    if rec["unaudited_reason"]:
        if rec["verdict"] is not None:
            raise ValueError(f"{where}: unaudited receipt carries a verdict")
    elif not isinstance(rec["verdict"], dict):
        raise ValueError(f"{where}: receipt has neither a verdict nor an unaudited reason")


def _version_of(rec: dict):
    version = rec.get("receipt_version")
    return version if isinstance(version, int) and not isinstance(version, bool) else None


def check_structure(rec: dict, where: str = "receipt") -> None:
    """Per-receipt structural verification for any supported version."""
    version = _version_of(rec)
    if version == RECEIPT_VERSION:
        _check_v3_structure(rec, where)
    elif version in (1, 2):
        _check_legacy_structure(rec, where, version)
    else:
        raise ValueError(f"{where}: unknown receipt_version {rec.get('receipt_version')!r}")


def _check_file(entries: list, path) -> None:
    versions = sorted({rec["receipt_version"] for _, rec in entries})
    if len(versions) > 1:
        raise ValueError(f"{path}: mixed receipt versions {versions} in one file "
                         f"(a file holds one version; downgraded or spliced receipts)")
    if versions != [RECEIPT_VERSION]:
        return
    prev = GENESIS
    for lineno, rec in entries:
        if rec["prev_receipt_sha256"] != prev:
            raise ValueError(f"{path}:{lineno}: hash chain broken (a receipt was "
                             f"deleted, inserted or reordered)")
        prev = rec["receipt_id"]
    seen = {}
    for lineno, rec in entries:
        if rec["paper_id"] is None:
            continue  # ad-hoc scans may judge the same case again
        key = (rec["paper_id"], rec["case_id"], rec["arm"], rec["run"], rec["attempt"])
        if key in seen:
            raise ValueError(f"{path}:{lineno}: duplicate attempt {list(key)} "
                             f"(first at line {seen[key]})")
        seen[key] = lineno


def load_receipts(path) -> list[dict]:
    """Read and structurally verify a receipts file (every line and the file)."""
    entries = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: not JSON: {exc}") from exc
            if not isinstance(rec, dict):
                raise ValueError(f"{path}:{lineno}: not a JSON object")
            check_structure(rec, f"{path}:{lineno}")
            entries.append((lineno, rec))
    _check_file(entries, path)
    return [rec for _, rec in entries]


def _label(rec: dict) -> str:
    label = f"{rec.get('case_id')}/{rec.get('arm')}"
    if "attempt" in rec:
        label += f"/run {rec.get('run')}/attempt {rec.get('attempt')}"
    return label


def _verify_content_v2(rec: dict, mechanism_classes) -> None:
    """Round-2 rules, plus: the embedded texts must be present (no downgrade)."""
    label = _label(rec)
    for key in V2_CONTENT_FIELDS:
        if not isinstance(rec.get(key), str):
            raise ValueError(f"{label}: v2 receipt lacks embedded {key} (content stripped)")
    if hashlib.sha256(rec["prompt_text"].encode()).hexdigest() != rec["prompt_sha256"]:
        raise ValueError(f"{label}: prompt hash mismatch")
    if hashlib.sha256(rec["anchor_text"].encode()).hexdigest() != rec["anchor_sha256"]:
        raise ValueError(f"{label}: anchor hash mismatch")
    if rec["unaudited_reason"]:
        if rec["verdict"] is not None or rec["raw_response"] is not None:
            raise ValueError(f"{label}: unaudited receipt carries verdict/raw")
        return
    try:
        reparsed = validate_verdict(extract_json_v2(rec["raw_response"]), mechanism_classes)
    except Exception as exc:
        raise ValueError(f"{label}: raw response no longer parses: {exc}")
    if reparsed != rec["verdict"]:
        raise ValueError(f"{label}: re-parsed verdict differs from stored")


def _verify_content_v3(rec: dict, mechanism_classes) -> None:
    label = _label(rec)
    for key in V2_CONTENT_FIELDS:
        if not isinstance(rec.get(key), str):
            raise ValueError(f"{label}: receipt lacks embedded {key}")
    if hashlib.sha256(rec["prompt_text"].encode("utf-8")).hexdigest() != rec["prompt_sha256"]:
        raise ValueError(f"{label}: prompt hash mismatch")
    if hashlib.sha256(rec["anchor_text"].encode("utf-8")).hexdigest() != rec["anchor_sha256"]:
        raise ValueError(f"{label}: anchor hash mismatch")
    if rec.get("prompt_version") != PROMPT_VERSION:
        raise ValueError(f"{label}: prompt version {rec.get('prompt_version')!r} cannot be "
                         f"checked by this build (it knows v{PROMPT_VERSION})")
    if rec["prompt_text"] != render_prompt(rec["anchor_text"]):
        raise ValueError(f"{label}: prompt_text is not the pinned instruction header "
                         f"plus the anchor text")
    if rec.get("anchor_version") != ANCHOR_VERSION:
        raise ValueError(f"{label}: anchor version {rec.get('anchor_version')!r} cannot be "
                         f"checked by this build (it knows v{ANCHOR_VERSION})")
    try:
        parse_anchor(rec["anchor_text"])  # stamps, own END markers, escaping (CR-04)
    except ValueError as exc:
        raise ValueError(f"{label}: anchor_text is not a well-formed anchor "
                         f"v{ANCHOR_VERSION}: {exc}") from exc
    if rec.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{label}: verdict schema {rec.get('schema_version')!r} is not "
                         f"v{SCHEMA_VERSION}")
    options = rec.get("options") if isinstance(rec.get("options"), dict) else {}
    generation = rec.get("generation") if isinstance(rec.get("generation"), dict) else {}
    transport = rec.get("transport") if isinstance(rec.get("transport"), dict) else {}
    pin, pin_after = rec.get("pin") or {}, rec.get("pin_after")
    if rec["unaudited_reason"]:
        if rec["verdict"] is not None:
            raise ValueError(f"{label}: unaudited receipt carries a verdict")
        if rec["raw_response"] is not None and not isinstance(rec["raw_response"], str):
            raise ValueError(f"{label}: raw_response is not text")
        return
    # A valid verdict must not have slipped past the guards it was judged under.
    num_ctx, prompt_tokens = options.get("num_ctx"), generation.get("prompt_eval_count")
    if _is_pos_int(num_ctx) and isinstance(prompt_tokens, int) and prompt_tokens >= num_ctx:
        raise ValueError(f"{label}: valid verdict recorded with a full context")
    if generation.get("done_reason") == "length" or generation.get("truncated") is True:
        raise ValueError(f"{label}: valid verdict recorded from truncated output")
    if transport.get("name") == OLLAMA:
        if not isinstance(pin_after, dict):
            raise ValueError(f"{label}: local verdict without the post-judgment pin")
        if pin_after.get("manifest_digest") != pin.get("manifest_digest"):
            raise ValueError(f"{label}: valid verdict recorded across a digest change")
    if not isinstance(rec["raw_response"], str):
        raise ValueError(f"{label}: verdict without raw output")
    try:
        reparsed = validate_verdict(extract_json(rec["raw_response"]), mechanism_classes)
    except Exception as exc:
        raise ValueError(f"{label}: raw response no longer parses: {exc}")
    if reparsed != rec["verdict"]:
        raise ValueError(f"{label}: re-parsed verdict differs from stored")


def verify_content(rec: dict, mechanism_classes=None) -> None:
    """Content verification for one receipt. Raises ValueError on any
    disagreement between embedded content, recomputed hashes, and the
    stored verdict. This never calls a model; replay is not implemented.

    v1: no embedded content; nothing to check here. v2: round-2 rules.
    v3: hashes, prompt == pinned header + anchor, a well-formed anchor of the
    current version (parse_anchor), schema version, guard consistency,
    strict re-parse of the raw output.
    """
    classes = mechanism_classes if mechanism_classes is not None else MECHANISM_CLASSES
    version = _version_of(rec)
    if version == 1:
        return
    if version == 2:
        _verify_content_v2(rec, classes)
    elif version == RECEIPT_VERSION:
        _verify_content_v3(rec, classes)
    else:
        raise ValueError(f"{_label(rec)}: unknown receipt_version {rec.get('receipt_version')!r}")


def verify_file(path, mechanism_classes=None, content: bool = False,
                expect_head: str | None = None, expect_count: int | None = None) -> list[dict]:
    """Structural verification (always), optional content verification, and
    optional tail check against an externally recorded head and count."""
    receipts = load_receipts(path)
    if expect_count is not None and len(receipts) != expect_count:
        raise ValueError(f"{path}: {len(receipts)} receipts, expected {expect_count} "
                         f"(receipts removed or added)")
    if expect_head is not None:
        head = receipts[-1]["receipt_id"] if receipts else GENESIS
        if head != expect_head:
            raise ValueError(f"{path}: chain head is not the expected one "
                             f"(tail truncated or extended)")
    if content:
        for rec in receipts:
            verify_content(rec, mechanism_classes)
    return receipts
