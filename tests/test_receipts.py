"""Receipts: integrity hashing, append-only file, structural + content verification."""

import json

import pytest
from fakes import make_diff_case, verdict
from gavel.anchor import render_case, sha256_text
from gavel.prompt import MECHANISM_CLASSES, render_prompt
from gavel.receipts import (make_receipt, write_receipt, load_receipts,
                            verify_file, verify_content)

PIN = {"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:35b",
       "size_bytes": 1, "modified_at": "t"}


def one_receipt(case_id="T-1", with_content=True, raw='{"attack": true, "confidence": 0.9}',
                stored_verdict=None):
    case = make_diff_case(case_id=case_id)
    anchor = render_case(case)
    prompt = render_prompt(anchor)
    if with_content:
        return make_receipt(
            case_id, "primary", PIN, sha256_text(prompt), sha256_text(anchor),
            raw, stored_verdict if stored_verdict is not None else verdict("clean"),
            None, prompt_text=prompt, anchor_text=anchor,
            execution={"schema_version": 2, "temperature": 0})
    return make_receipt(case_id, "primary", PIN, sha256_text(prompt),
                        sha256_text(anchor), raw, verdict("clean"), None)


def test_receipt_roundtrip(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt())
    write_receipt(path, one_receipt(case_id="T-2"))
    receipts = verify_file(path)
    assert [r["case_id"] for r in receipts] == ["T-1", "T-2"]


def test_receipt_id_is_content_hash():
    assert one_receipt()["receipt_id"] == one_receipt()["receipt_id"]


def test_tampered_case_id_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt())
    rec = load_receipts(path)[0]
    rec["case_id"] = "FORGED"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True))
    with pytest.raises(ValueError, match="receipt_id mismatch"):
        verify_file(path)


def test_truncated_line_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    path.write_text('{"receipt_version": 1, "case_id": "x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        verify_file(path)


def test_content_verification_passes(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt(raw=json.dumps(verdict("clean")),
                                    stored_verdict=verdict("clean")))
    assert verify_file(path, MECHANISM_CLASSES, content=True)


def test_content_tampering_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt(raw=json.dumps(verdict("clean")),
                                    stored_verdict=verdict("clean")))
    rec = load_receipts(path)[0]
    rec["prompt_text"] = rec["prompt_text"].replace("verification", "VERIFICATION")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True))
    with pytest.raises(ValueError, match="prompt hash mismatch"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_stored_verdict_must_match_reparsed_raw(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt(raw=json.dumps(verdict("clean")),
                                    stored_verdict=verdict("attack")))
    with pytest.raises(ValueError, match="re-parsed verdict differs"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_unparseable_raw_fails_content_verification(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt(raw="garbage", stored_verdict=verdict("clean")))
    with pytest.raises(ValueError, match="no longer parses"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_legacy_receipt_skips_content_checks(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt(with_content=False))
    assert verify_file(path, MECHANISM_CLASSES, content=True)


def test_unaudited_receipt_content_rules(tmp_path):
    case = make_diff_case()
    anchor = render_case(case)
    prompt = render_prompt(anchor)
    rec = make_receipt(case["case_id"], "primary", PIN, sha256_text(prompt),
                       sha256_text(anchor), None, None, "model unreachable",
                       prompt_text=prompt, anchor_text=anchor,
                       execution={"schema_version": 2})
    assert rec["verdict"] is None and rec["unaudited_reason"]
    verify_content(rec, MECHANISM_CLASSES)  # OK
    rec["verdict"] = verdict("clean")  # unaudited must not carry a verdict
    with pytest.raises(ValueError, match="carries verdict"):
        verify_content(rec, MECHANISM_CLASSES)
