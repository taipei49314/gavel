"""Receipts: integrity hashing, append-only file, structural verification."""

import pytest
from fakes import make_diff_case, verdict
from gavel.anchor import render_case, sha256_text
from gavel.prompt import render_prompt
from gavel.receipts import make_receipt, write_receipt, load_receipts, verify_file


PIN = {"model": "qwen3.5:35b-a3b", "config_digest": "sha256:cfg",
       "layer_digests": ["sha256:l1"]}


def one_receipt(case_id="T-1"):
    case = make_diff_case(case_id=case_id)
    anchor = render_case(case)
    prompt = render_prompt(anchor)
    return make_receipt(case_id, "primary", PIN, sha256_text(prompt),
                        sha256_text(anchor), '{"attack": false}', verdict(), None)


def test_receipt_roundtrip(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt())
    write_receipt(path, one_receipt(case_id="T-2"))
    receipts = verify_file(path)
    assert [r["case_id"] for r in receipts] == ["T-1", "T-2"]


def test_receipt_id_is_content_hash():
    a, b = one_receipt(), one_receipt()
    assert a["receipt_id"] == b["receipt_id"]


def test_tampered_case_id_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_receipt(path, one_receipt())
    rec = load_receipts(path)[0]
    rec["case_id"] = "FORGED"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json_dumps(rec))
    with pytest.raises(ValueError, match="receipt_id mismatch"):
        verify_file(path)


def test_truncated_line_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    path.write_text('{"receipt_version": 1, "case_id": "x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        verify_file(path)


def test_unaudited_receipt_is_recordable(tmp_path):
    case = make_diff_case()
    anchor = render_case(case)
    prompt = render_prompt(anchor)
    rec = make_receipt(case["case_id"], "primary", PIN, sha256_text(prompt),
                       sha256_text(anchor), None, None, "model unreachable")
    assert rec["verdict"] is None and rec["unaudited_reason"]


def json_dumps(obj):
    import json
    return json.dumps(obj, sort_keys=True)
