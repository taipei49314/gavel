"""Receipts: v3 full-body ids, per-file hash chain, downgrade refusal, content
verification; v1/v2 receipts keep the rules they were written under.

Covers CR-06 (pin bound, run/attempt bound, deletions, reordering and
downgrades detected, prompt checked against the pinned header), CR-07
(raw output kept on UNAUDITED), R2-12 (receipt_id unique per receipt) and
GOV-12 (host, runtime, options, transport recorded).
"""

import json
from pathlib import Path

import gavel
import pytest
from fakes import (APPROVED_BY, fake_judgment, legacy_receipt, make_diff_case,
                   verdict, write_lines)
from gavel.anchor import render_case_v1, sha256_text
from gavel.prompt import MECHANISM_CLASSES, render_prompt
from gavel.receipts import (GENESIS, RECEIPT_VERSION, ReceiptLog,
                            append_receipt, build_receipt, receipt_digest,
                            seal_receipt, verify_content, verify_file)

HOST = {"hostname": "pool-host-1", "node": "pool-host-1", "system": "Windows",
        "python": "3.12.10"}
REPO_ROOT = Path(gavel.__file__).resolve().parent.parent


def body(case_id="T-1", run=1, attempt=1, paper_id="paper-x", timestamp="2026-10-20T00:00:00+00:00",
         host=None, **judgment_kw):
    return build_receipt(case_id=case_id, arm="primary", run=run, attempt=attempt,
                         judgment=fake_judgment(make_diff_case(case_id=case_id), **judgment_kw),
                         paper_id=paper_id, case_sha256="c" * 64,
                         timestamp=timestamp, host=host or HOST)


def write_chain(path, bodies):
    log = ReceiptLog(path)
    return [log.append(b) for b in bodies]


def rewrite(path, receipts):
    write_lines(path, receipts)


# --- v3 structure and chain -------------------------------------------------

def test_v3_roundtrip_and_chain(tmp_path):
    path = tmp_path / "receipts.jsonl"
    written = write_chain(path, [body("T-1"), body("T-2"), body("T-3")])
    receipts = verify_file(path, MECHANISM_CLASSES, content=True)
    assert [r["case_id"] for r in receipts] == ["T-1", "T-2", "T-3"]
    assert receipts[0]["prev_receipt_sha256"] == GENESIS
    assert receipts[1]["prev_receipt_sha256"] == written[0]["receipt_id"]
    assert receipts[2]["prev_receipt_sha256"] == written[1]["receipt_id"]
    assert all(r["receipt_version"] == RECEIPT_VERSION for r in receipts)


def test_v3_records_host_runtime_options_transport(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = write_chain(path, [body()])[0]
    assert rec["host"] == HOST
    assert rec["approved_models"] == APPROVED_BY
    assert rec["transport"] == {"name": "ollama", "version": "0.35.0"}
    assert rec["options"]["num_ctx"] == 16384 and rec["options"]["temperature"] == 0
    assert rec["pin"]["manifest_digest"] == rec["pin_after"]["manifest_digest"]
    assert rec["generation"]["prompt_eval_count"] == 120
    assert rec["paper_id"] == "paper-x" and rec["case_sha256"] == "c" * 64


def test_default_host_is_read_from_the_machine():
    b = build_receipt(case_id="T-1", arm="primary", run=1, attempt=1,
                      judgment=fake_judgment())
    assert set(b["host"]) == {"hostname", "node", "system", "python"}
    assert b["host"]["hostname"]


def test_receipt_id_binds_run_attempt_timestamp_and_host():
    base = seal_receipt(body(), GENESIS)["receipt_id"]
    assert len(base) == 64
    assert seal_receipt(body(run=2), GENESIS)["receipt_id"] != base
    assert seal_receipt(body(attempt=2), GENESIS)["receipt_id"] != base
    assert seal_receipt(body(timestamp="2026-10-21T00:00:00+00:00"), GENESIS)["receipt_id"] != base
    assert seal_receipt(body(host={**HOST, "hostname": "other"}), GENESIS)["receipt_id"] != base
    assert seal_receipt(body(), GENESIS)["receipt_id"] == base


def test_build_receipt_rejects_bad_run_or_attempt():
    for bad in (0, -1, True, "1", None):
        with pytest.raises(ValueError):
            build_receipt(case_id="T-1", arm="primary", run=1, attempt=bad,
                          judgment=fake_judgment())
        with pytest.raises(ValueError):
            build_receipt(case_id="T-1", arm="primary", run=bad, attempt=1,
                          judgment=fake_judgment())


@pytest.mark.parametrize("field,value", [
    ("case_id", "FORGED"), ("run", 3), ("attempt", 1), ("timestamp", "2026-01-01T00:00:00+00:00"),
    ("host", {"hostname": "elsewhere"}), ("execution", {"timeout_s": 1}),
    ("raw_response", "{}"), ("unaudited_reason", "x"),
])
def test_any_field_edit_breaks_receipt_id(tmp_path, field, value):
    path = tmp_path / "receipts.jsonl"
    rec = write_chain(path, [body(attempt=2)])[0]
    rec[field] = value
    rewrite(path, [rec])
    with pytest.raises(ValueError, match="receipt_id mismatch"):
        verify_file(path)


def test_pin_edit_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = write_chain(path, [body()])[0]
    rec["pin"]["manifest_digest"] = "sha256:other"
    rec["receipt_id"] = receipt_digest(rec)  # even with a recomputed id
    rewrite(path, [rec])
    with pytest.raises(ValueError, match="pin_sha256 does not match pin"):
        verify_file(path)


def test_deleted_line_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    recs = write_chain(path, [body("T-1"), body("T-2"), body("T-3")])
    rewrite(path, [recs[0], recs[2]])
    with pytest.raises(ValueError, match="hash chain broken"):
        verify_file(path)


def test_deleted_first_line_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    recs = write_chain(path, [body("T-1"), body("T-2")])
    rewrite(path, [recs[1]])
    with pytest.raises(ValueError, match="hash chain broken"):
        verify_file(path)


def test_reordered_lines_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    recs = write_chain(path, [body("T-1"), body("T-2"), body("T-3")])
    rewrite(path, [recs[0], recs[2], recs[1]])
    with pytest.raises(ValueError, match="hash chain broken"):
        verify_file(path)


def test_truncated_tail_detected_with_expected_head_and_count(tmp_path):
    path = tmp_path / "receipts.jsonl"
    recs = write_chain(path, [body("T-1"), body("T-2"), body("T-3")])
    head = recs[-1]["receipt_id"]
    assert verify_file(path, expect_head=head, expect_count=3)
    rewrite(path, recs[:2])
    assert verify_file(path)  # the chain alone cannot see a cut tail
    with pytest.raises(ValueError, match="tail truncated"):
        verify_file(path, expect_head=head)
    with pytest.raises(ValueError, match="expected 3"):
        verify_file(path, expect_count=3)


def test_duplicate_paper_attempt_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body("T-1"), body("T-1")])
    with pytest.raises(ValueError, match="duplicate attempt"):
        verify_file(path)


def test_scan_receipts_may_judge_a_case_again(tmp_path):
    path = tmp_path / "scan.jsonl"
    append_receipt(path, body("T-1", paper_id=None))
    append_receipt(path, body("T-1", paper_id=None))
    assert len(verify_file(path, MECHANISM_CLASSES, content=True)) == 2


def test_unknown_field_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = write_chain(path, [body()])[0]
    rec["note"] = "completeness re-attempt of an invalid slot"
    rec["receipt_id"] = receipt_digest(rec)
    rewrite(path, [rec])
    with pytest.raises(ValueError, match="unknown fields"):
        verify_file(path)


def test_truncated_line_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    path.write_text('{"receipt_version": 1, "case_id": "x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        verify_file(path)


def test_unknown_version_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = legacy_receipt(version=2)
    rec["receipt_version"] = 9
    write_lines(path, [rec])
    with pytest.raises(ValueError, match="unknown receipt_version"):
        verify_file(path)


# --- downgrades -------------------------------------------------------------

def test_v2_line_in_v3_file_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    recs = write_chain(path, [body("T-1")])
    write_lines(path, recs + [legacy_receipt(version=2)])
    with pytest.raises(ValueError, match="mixed receipt versions"):
        verify_file(path)


def test_v1_and_v2_mixed_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_lines(path, [legacy_receipt(version=2), legacy_receipt(version=1)])
    with pytest.raises(ValueError, match="mixed receipt versions"):
        verify_file(path)


def test_v2_receipt_with_content_stripped_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = legacy_receipt(version=2)
    del rec["prompt_text"]
    del rec["anchor_text"]
    write_lines(path, [rec])
    with pytest.raises(ValueError, match="content stripped"):
        verify_file(path)
    with pytest.raises(ValueError, match="content stripped"):
        verify_content(rec, MECHANISM_CLASSES)


def test_v3_relabelled_as_v2_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = dict(write_chain(path, [body()])[0])
    rec["receipt_version"] = 2
    write_lines(path, [rec])
    with pytest.raises(ValueError, match="carries v3 fields"):
        verify_file(path)


def test_cannot_append_v3_to_a_legacy_file(tmp_path):
    path = tmp_path / "scan.jsonl"
    write_lines(path, [legacy_receipt(version=2)])
    with pytest.raises(ValueError, match="new file"):
        append_receipt(path, body())


def test_append_refuses_a_broken_chain(tmp_path):
    path = tmp_path / "receipts.jsonl"
    recs = write_chain(path, [body("T-1"), body("T-2"), body("T-3")])
    rewrite(path, [recs[0], recs[2]])
    with pytest.raises(ValueError, match="hash chain broken"):
        ReceiptLog(path)


# --- v3 content verification ------------------------------------------------

def test_v3_content_verification_passes(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(v="attack"), body("T-2", v="inconclusive")])
    assert len(verify_file(path, MECHANISM_CLASSES, content=True)) == 2


def test_v3_prompt_must_be_pinned_header_plus_anchor(tmp_path):
    path = tmp_path / "receipts.jsonl"
    b = body()
    b["prompt_text"] = b["prompt_text"].replace("verification auditor", "lenient auditor")
    import hashlib
    b["prompt_sha256"] = hashlib.sha256(b["prompt_text"].encode()).hexdigest()
    write_chain(path, [b])
    verify_file(path)  # self-consistent hashes pass the structural check
    with pytest.raises(ValueError, match="pinned instruction header"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def _with_anchor(b, anchor_text):
    b["anchor_text"] = anchor_text
    b["anchor_sha256"] = sha256_text(anchor_text)
    b["prompt_text"] = render_prompt(anchor_text)
    b["prompt_sha256"] = sha256_text(b["prompt_text"])
    return b


def test_v3_anchor_must_be_well_formed(tmp_path):
    # CR-04: a self-consistent receipt whose anchor text was edited (here the
    # diff block's END marker no longer repeats its stamp) fails content
    # verification.
    path = tmp_path / "receipts.jsonl"
    b = body()
    end = b["anchor_text"].index('<<<GAVEL:END id="diff" sha256="') + len(
        '<<<GAVEL:END id="diff" sha256="')
    forged = b["anchor_text"][:end] + "0" * 64 + b["anchor_text"][end + 64:]
    write_chain(path, [_with_anchor(b, forged)])
    verify_file(path)
    with pytest.raises(ValueError, match="not a well-formed anchor"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_anchor_version_must_be_current(tmp_path):
    path = tmp_path / "receipts.jsonl"
    b = body()
    b["anchor_version"] = 1
    write_chain(path, [b])
    with pytest.raises(ValueError, match="anchor version 1"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_v1_anchor_text_refused(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [_with_anchor(body(), render_case_v1(make_diff_case()))])
    with pytest.raises(ValueError, match="not a well-formed anchor"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_stored_verdict_must_match_reparsed_raw(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(v="clean", stored=verdict("attack"))])
    with pytest.raises(ValueError, match="re-parsed verdict differs"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_raw_with_prose_fails_strict_reparse(tmp_path):
    path = tmp_path / "receipts.jsonl"
    raw = "Sure.\n```json\n" + json.dumps(verdict("clean")) + "\n```"
    write_chain(path, [body(v="clean", raw=raw)])
    with pytest.raises(ValueError, match="no longer parses"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_unaudited_keeps_raw(tmp_path):
    path = tmp_path / "receipts.jsonl"
    eight_keys = verdict("clean")
    del eight_keys["missing_evidence"]
    raw = json.dumps(eight_keys)
    rec = write_chain(path, [body(unaudited="verdict keys mismatch", raw=raw)])[0]
    assert rec["raw_response"] == raw and rec["verdict"] is None
    verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_unaudited_with_verdict_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(unaudited="empty model response", raw="",
                            stored=verdict("clean"))])
    with pytest.raises(ValueError, match="unaudited receipt carries a verdict"):
        verify_file(path)


def test_v3_verdict_with_full_context_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(generation={"prompt_eval_count": 16384, "done_reason": "stop"})])
    with pytest.raises(ValueError, match="full context"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_verdict_across_digest_change_rejected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(pin_after={"model": "qwen3.5:35b-a3b",
                                       "manifest_digest": "sha256:repulled"})])
    with pytest.raises(ValueError, match="digest change"):
        verify_file(path, MECHANISM_CLASSES, content=True)


@pytest.mark.parametrize("generation", [
    {"eval_count": 60, "done": True, "done_reason": "stop"},
    {"prompt_eval_count": 0, "done_reason": "stop"},
    {"prompt_eval_count": None, "done_reason": "stop"},
])
def test_v3_local_verdict_without_prompt_count_rejected(tmp_path, generation):
    # CR-16: generate() refuses such a response, so a valid local verdict
    # recorded without a positive prompt_eval_count did not pass that guard.
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(generation=generation)])
    verify_file(path)  # structurally fine
    with pytest.raises(ValueError, match="positive prompt_eval_count"):
        verify_file(path, MECHANISM_CLASSES, content=True)


@pytest.mark.parametrize("approved", [None, {}, {"file": "approved-models.json"},
                                      {"file": "", "sha256": "a" * 64},
                                      {"file": "approved-models.json", "sha256": "A" * 64}])
def test_v3_verdict_without_the_approving_file_rejected(tmp_path, approved):
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(approved_models=approved)])
    with pytest.raises(ValueError, match="approved-models file"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v3_unaudited_receipt_needs_no_approving_file(tmp_path):
    # A judgment refused by the approved-models check has none to record.
    path = tmp_path / "receipts.jsonl"
    write_chain(path, [body(unaudited="model/pin not in approved manifest", approved_models=None,
                            generation={})])
    rec = verify_file(path, MECHANISM_CLASSES, content=True)[0]
    assert rec["approved_models"] is None


def test_v3_cloud_receipt_needs_no_post_pin(tmp_path):
    path = tmp_path / "receipts.jsonl"
    b = build_receipt(case_id="T-1", arm="informed", run=1, attempt=1,
                      judgment=fake_judgment(transport_name="agy",
                                             generation={"exit_code": 0}), host=HOST)
    write_chain(path, [b])
    rec = verify_file(path, MECHANISM_CLASSES, content=True)[0]
    assert rec["execution"] == {"timeout_s": 600.0} and rec["options"] == {}
    assert rec["generation"] == {"exit_code": 0}  # no Ollama token counts for agy


def test_receipt_lines_are_read_strictly(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = write_chain(path, [body()])[0]
    line = json.dumps(rec, sort_keys=True)
    # A duplicate key: a plain reader would keep the last value.
    path.write_text(line[:-1] + ', "arm": "primary"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="not strict JSON: duplicate key 'arm'"):
        verify_file(path)


# --- v1/v2 keep their own rules ------------------------------------------------

def test_v2_content_verification_old_rules(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_lines(path, [legacy_receipt(version=2)])
    assert verify_file(path, MECHANISM_CLASSES, content=True)


def test_v2_raw_reparsed_with_round2_extractor(tmp_path):
    path = tmp_path / "receipts.jsonl"
    raw = "Sure.\n```json\n" + json.dumps(verdict("clean")) + "\n```\nDone."
    write_lines(path, [legacy_receipt(version=2, raw=raw)])
    assert verify_file(path, MECHANISM_CLASSES, content=True)


def test_v2_tampered_prompt_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = legacy_receipt(version=2)
    rec["prompt_text"] = rec["prompt_text"].replace("verification", "VERIFICATION")
    write_lines(path, [rec])
    with pytest.raises(ValueError, match="prompt hash mismatch"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v2_stored_verdict_must_match_reparsed_raw(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_lines(path, [legacy_receipt(version=2, stored=verdict("attack"))])
    with pytest.raises(ValueError, match="re-parsed verdict differs"):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_v2_unaudited_with_raw_rejected_under_old_rules():
    rec = legacy_receipt(version=2, unaudited="model unreachable")
    verify_content(rec, MECHANISM_CLASSES)
    rec["raw_response"] = "partial"
    with pytest.raises(ValueError, match="carries verdict/raw"):
        verify_content(rec, MECHANISM_CLASSES)


def test_v2_pin_edit_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = legacy_receipt(version=2)
    rec["pin"]["manifest_digest"] = "sha256:other"
    write_lines(path, [rec])
    with pytest.raises(ValueError, match="pin_sha256 does not match pin"):
        verify_file(path)


def test_v2_tampered_case_id_detected(tmp_path):
    path = tmp_path / "receipts.jsonl"
    rec = legacy_receipt(version=2)
    rec["case_id"] = "FORGED"
    write_lines(path, [rec])
    with pytest.raises(ValueError, match="receipt_id mismatch"):
        verify_file(path)


def test_v1_gets_structural_checks_only(tmp_path):
    path = tmp_path / "receipts.jsonl"
    write_lines(path, [legacy_receipt(version=1, raw='{"attack": true, "confidence": 0.9}')])
    assert verify_file(path, MECHANISM_CLASSES, content=True)


COMMITTED_RECEIPTS = [
    "results/round-0/receipts.jsonl",
    "results/round-0/receipts-rerun-LWR1.jsonl",
    "results/round-1/receipts.jsonl",
    "attack/round-1/receipts.jsonl",
    "results/round-2/regression/receipts.jsonl",
    "results/round-2/sealed/receipts.jsonl",
]


@pytest.mark.parametrize("relpath", COMMITTED_RECEIPTS)
def test_committed_receipts_still_verify(relpath):
    receipts = verify_file(REPO_ROOT / relpath, MECHANISM_CLASSES, content=True)
    assert receipts and len({r["receipt_version"] for r in receipts}) == 1
