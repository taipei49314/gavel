"""The single judgment path (judge_case) shared by exam and scan, and the
committed exam driver (run_paper).

Covers CR-02/F4 (approved-models checked on every judgment, default path
not CWD, the approving file recorded by name and sha256), the digest and
runtime version read before and after each judgment, CR-07 (raw output kept
on UNAUDITED), CR-14 (transport errors and any other exception are
UNAUDITED, never an abort), CR-16 (truncation guard, options recorded),
GOV-12 (execution facts per transport), and CR-01/CR-03 for the driver
(harness-only attempts within the cap, every attempt receipted, one run per
output directory with a "started" marker, its report reproducible from its
receipts, receipts bound to their locked case files).
"""

import hashlib
import json
import urllib.error

import pytest
from fakes import (FakeTransport, fake_judgment, legacy_receipt, load_json,
                   make_diff_case, make_ledger_case, marked_case, marker,
                   raising, verdict, write_approved, write_paper)
from gavel import qualify
from gavel.anchor import ANCHOR_VERSION
from gavel.cli import main
from gavel.judge import DEFAULT_NUM_CTX, SCHEMA_VERSION, UnauditedError
from gavel.prompt import MECHANISM_CLASSES, PROMPT_VERSION
from gavel.qualify import (PaperError, check_receipts_against_paper, evaluate,
                           judge_case, load_paper, records_from_receipts,
                           run_paper)
from gavel.receipts import verify_file

PRIMARY = "qwen3.5:35b-a3b"
FAST = "qwen3.5:9b"
INFORMED = "gemini-4-argon-high"


@pytest.fixture
def approved(tmp_path):
    return write_approved(tmp_path)


def good_transport(**kw):
    return FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("attack")),
                                            FAST: json.dumps(verdict("clean"))}, **kw)


def test_success_records_every_receipt_fact(approved):
    t = good_transport(version="0.35.0")
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["unaudited"] is None and res["verdict"]["verdict"] == "attack"
    assert res["raw"] == json.dumps(verdict("attack"))
    assert res["prompt_text"] and res["anchor_text"]
    assert res["pin"]["manifest_digest"] == "sha256:35b"
    assert res["pin_after"]["manifest_digest"] == "sha256:35b"
    assert res["transport"] == {"name": "ollama", "version": "0.35.0"}
    assert res["options"] == {"temperature": 0, "num_ctx": DEFAULT_NUM_CTX}
    assert res["generation"]["prompt_eval_count"] == 120
    assert res["execution"] == {"base_url": "http://x", "timeout_s": 5}
    assert (res["prompt_version"], res["anchor_version"], res["schema_version"]) == \
        (PROMPT_VERSION, ANCHOR_VERSION, SCHEMA_VERSION)
    # Which approved-models file gated the judgment, by name and content hash.
    assert res["approved_models"] == {"file": "approved-models.json",
                                      "sha256": hashlib.sha256(approved.read_bytes()).hexdigest()}


def test_fake_judgment_has_the_judge_case_shape(approved):
    # Receipt tests build judgments with fakes.fake_judgment; keep its shape
    # identical to the real judgment path.
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=good_transport(),
                     approved_models=approved)
    assert set(fake_judgment()) == set(res)
    assert set(fake_judgment()["transport"]) == set(res["transport"])


def test_unreachable_model_is_unaudited(approved):
    dead = FakeTransport(response_by_model={})
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=dead,
                     approved_models=approved)
    assert res["verdict"] is None and "unreachable" in res["unaudited"]


def test_ledger_case_judges_through_same_path(approved):
    t = FakeTransport(response_by_model={
        PRIMARY: json.dumps(verdict(
            "attack", mechanism="ledger-structure-evasion",
            element="governance/tasks/archive/T-9.json"))})
    res = judge_case(make_ledger_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["verdict"]["mechanism_class"] == "ledger-structure-evasion"


# --- approved-models on every judgment (CR-02, F4) ------------------------

def test_unapproved_digest_is_unaudited_before_any_generate(tmp_path):
    path = write_approved(tmp_path, [
        {"model": PRIMARY, "manifest_digest": "sha256:other", "transport": "ollama"}])
    t = good_transport()
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=path)
    assert res["verdict"] is None and "not in approved manifest" in res["unaudited"]
    assert t.generate_calls() == []
    assert res["approved_models"] is None  # nothing approved this judgment
    # The pin that was actually present is recorded, not blanked (CR-14).
    assert res["pin"]["manifest_digest"] == "sha256:35b"


def test_default_approved_path_is_used_when_none_given():
    # No approved_models argument: the repo-root approved-models.json is
    # used, which does not approve the fake digest. The check is never
    # skipped.
    t = good_transport()
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t)
    assert res["verdict"] is None and "not in approved manifest" in res["unaudited"]
    assert t.generate_calls() == []


def test_missing_approved_file_is_unaudited(tmp_path):
    t = good_transport()
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=tmp_path / "absent.json")
    assert res["verdict"] is None and "unreadable" in res["unaudited"]
    assert t.generate_calls() == []


def test_digest_change_during_judgment_is_unaudited_and_keeps_raw(approved):
    t = good_transport(digest_after_generate={PRIMARY: "sha256:repulled"})
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["verdict"] is None and "digest changed" in res["unaudited"]
    assert res["raw"] == json.dumps(verdict("attack"))
    assert res["pin_after"]["manifest_digest"] == "sha256:repulled"


def test_runtime_change_during_judgment_is_unaudited(approved):
    t = good_transport(version="0.35.0", version_after_generate="0.40.4")
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["verdict"] is None and "version changed" in res["unaudited"]
    assert res["raw"] is not None


def test_pinned_runtime_mismatch_is_unaudited(approved):
    t = good_transport(version="0.40.4")
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved, pinned_runtime={"ollama_version": "0.35.0"})
    assert res["verdict"] is None and "not the pinned" in res["unaudited"]
    assert t.generate_calls() == []
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=good_transport(
        version="0.35.0"), approved_models=approved,
        pinned_runtime={"ollama_version": "0.35.0"})
    assert res["unaudited"] is None


# --- CR-07: raw output kept on UNAUDITED ----------------------------------

def test_schema_failure_keeps_raw(approved):
    eight_keys = verdict("clean")
    del eight_keys["missing_evidence"]
    raw = json.dumps(eight_keys)
    t = FakeTransport(response_by_model={FAST: raw})
    res = judge_case(make_diff_case(), FAST, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["verdict"] is None and "verdict keys mismatch" in res["unaudited"]
    assert res["raw"] == raw


def test_unparseable_output_keeps_raw(approved):
    t = FakeTransport(response_by_model={FAST: "I think this is fine."})
    res = judge_case(make_diff_case(), FAST, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["verdict"] is None and res["raw"] == "I think this is fine."


# --- CR-14 and CR-16 through the judgment path ------------------------------

def test_daemon_down_is_unaudited_not_an_exception(approved):
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5,
                     transport=raising(urllib.error.URLError("refused")),
                     approved_models=approved)
    assert res["verdict"] is None and "daemon unreachable" in res["unaudited"]


def test_generate_fn_raising_transport_error_is_unaudited(approved):
    def broken(model, prompt, base_url, timeout_s, transport=None, options=None):
        raise UnicodeDecodeError("utf-8", b"\x9d", 0, 1, "invalid start byte")
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=good_transport(),
                     approved_models=approved, generate_fn=broken)
    assert res["verdict"] is None and "transport error" in res["unaudited"]


def test_unexpected_exception_is_unaudited_not_an_abort(approved):
    # Any other exception ends as an UNAUDITED result, so run_paper can
    # receipt the attempt and go on instead of stopping mid-paper.
    def broken(model, prompt, base_url, timeout_s, transport=None, options=None):
        raise RecursionError("maximum recursion depth exceeded")
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=good_transport(),
                     approved_models=approved, generate_fn=broken)
    assert res["verdict"] is None
    assert res["unaudited"] == "internal error: RecursionError: maximum recursion depth exceeded"


def test_deeply_nested_output_is_unaudited(approved):
    depth = 100_000
    nested = '{"a": ' + "[" * depth + "]" * depth + "}"
    t = FakeTransport(response_by_model={PRIMARY: nested})
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["verdict"] is None and "no parseable JSON verdict" in res["unaudited"]
    assert res["raw"] == nested


def test_full_context_is_unaudited_with_counts_recorded(approved):
    t = good_transport(extra={"prompt_eval_count": DEFAULT_NUM_CTX + 5})
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["verdict"] is None and "context full" in res["unaudited"]
    assert res["generation"]["prompt_eval_count"] == DEFAULT_NUM_CTX + 5
    assert res["raw"] is not None


def test_manifest_options_reach_the_daemon_and_the_result(approved):
    t = good_transport()
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved, options={"num_ctx": 32768, "seed": 1})
    assert res["options"] == {"temperature": 0, "num_ctx": 32768, "seed": 1}
    assert t.generate_calls()[0][2]["options"] == res["options"]


# --- cloud transports (GOV-12: execution facts per transport) ------------

def test_cloud_transport_records_no_ollama_settings(approved):
    calls = []

    def fake_agy(model, prompt, base_url, timeout_s, transport=None, options=None):
        calls.append(options)
        return {"raw": json.dumps(verdict("clean")) + "\n", "generation": {},
                "transport_version": "1.3.5"}
    res = judge_case(make_diff_case(), INFORMED, "http://x", 5, approved_models=approved,
                     generate_fn=fake_agy, transport_name="agy")
    assert res["unaudited"] is None and res["verdict"]["verdict"] == "clean"
    assert res["pin"] == {"model": INFORMED, "manifest_digest": None, "transport": "agy"}
    assert res["pin_after"] is None
    assert res["options"] == {} and calls == [None]
    assert res["execution"] == {"timeout_s": 5}
    assert res["transport"] == {"name": "agy", "version": "1.3.5"}


def test_cloud_model_not_approved_is_unaudited(tmp_path):
    path = write_approved(tmp_path, [])
    res = judge_case(make_diff_case(), INFORMED, "http://x", 5, approved_models=path,
                     generate_fn=lambda *a, **k: {"raw": "{}"}, transport_name="agy")
    assert res["verdict"] is None and "not in approved manifest" in res["unaudited"]


def test_unknown_transport_is_unaudited(approved):
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, approved_models=approved,
                     transport_name="carrier-pigeon")
    assert res["verdict"] is None and "unknown transport" in res["unaudited"]


def test_transport_returning_no_text_is_unaudited(approved):
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=good_transport(),
                     approved_models=approved,
                     generate_fn=lambda *a, **k: "bare string, not the protocol dict")
    assert res["verdict"] is None and "no text" in res["unaudited"]


# --- run_paper: the committed exam driver (CR-01, CR-03) ----------------------

HOST = {"hostname": "pool-host-1", "node": "pool-host-1", "system": "Windows",
        "python": "3.12.10"}
PAPER_CASES = {
    "S-1": marked_case("S-1", tier="S"),
    "A-1": marked_case("A-1", tier="A"),
    "NEG-1": marked_case("NEG-1", tier=None, role="negative", attack_truth=False),
}


def responder(overrides=None):
    """Attack on every case except NEG-1 (clean); overrides maps
    (model, case_id) to a list of items consumed one per call."""
    overrides = overrides or {}
    calls = {}

    def respond(model, prompt):
        cid = next(c for c in PAPER_CASES if marker(c) in prompt)
        key = (model, cid)
        if key in overrides:
            index = calls.get(key, 0)
            calls[key] = index + 1
            seq = overrides[key]
            return seq[min(index, len(seq) - 1)]
        return json.dumps(verdict("clean" if cid == "NEG-1" else "attack"))
    return respond


@pytest.fixture
def paper_env(tmp_path):
    manifest_path = write_paper(tmp_path / "paper", PAPER_CASES)
    approved = write_approved(tmp_path)
    return manifest_path, approved, tmp_path / "out"


def run(paper_env, transport, **kw):
    manifest_path, approved, out = paper_env
    return run_paper(manifest_path, out, base_url="http://x", timeout_s=5,
                     approved_path=approved, transport=transport, host=HOST, **kw)


def receipts_of(paper_env):
    return verify_file(paper_env[2] / "receipts.jsonl", MECHANISM_CLASSES, content=True)


def test_run_paper_pass_writes_receipts_results_and_report(paper_env):
    t = FakeTransport(responder=responder())
    result = run(paper_env, t)
    assert result["report"]["status"] == "PASS", result["report"]
    # primary: S-1 x3 + A-1 + NEG-1; fast: 3 cases x1
    receipts = verify_file(paper_env[2] / "receipts.jsonl", MECHANISM_CLASSES, content=True,
                           expect_head=result["results"]["receipts"]["head"],
                           expect_count=8)
    assert all(r["attempt"] == 1 and r["paper_id"] == "test-paper" for r in receipts)
    assert all(r["host"] == HOST for r in receipts)
    assert [r["arm"] for r in receipts[:5]] == ["primary"] * 5  # gating arm first
    assert load_json(paper_env[2] / "report.json") == result["report"]
    results = load_json(paper_env[2] / "results.json")
    assert results["receipts"]["count"] == 8
    assert results["manifest_sha256"] == load_paper(paper_env[0])["manifest_sha256"]
    assert results["run_state"] == "finished"
    approved_by = {"file": "approved-models.json",
                   "sha256": hashlib.sha256(paper_env[1].read_bytes()).hexdigest()}
    assert results["approved_models"] == approved_by
    assert all(r["approved_models"] == approved_by for r in receipts)


def test_report_is_reproducible_from_receipts(paper_env):
    result = run(paper_env, FakeTransport(responder=responder()))
    manifest = load_paper(paper_env[0])["manifest"]
    assert evaluate(manifest, records_from_receipts(receipts_of(paper_env))) == result["report"]


def test_unaudited_slot_is_reattempted_immediately_and_disclosed(paper_env):
    t = FakeTransport(responder=responder({
        ("qwen3.5:9b", "A-1"): ["", json.dumps(verdict("attack"))]}))
    result = run(paper_env, t)
    report = result["report"]
    assert report["status"] == "PASS"
    assert report["reattempted"] == [{"cell": ["A-1", "fast", 1], "attempts": 2,
                                      "counted_attempt": 2,
                                      "unaudited_reasons": ["empty model response"]}]
    receipts = receipts_of(paper_env)
    slot = [r for r in receipts if (r["case_id"], r["arm"]) == ("A-1", "fast")]
    assert [r["attempt"] for r in slot] == [1, 2]
    assert slot[0]["unaudited_reason"] == "empty model response"
    assert slot[0]["raw_response"] == ""  # CR-07: what came back is kept
    assert len(receipts) == 9
    assert sum(1 for r in receipts if r["attempt"] > 1) == 1


def test_valid_verdicts_are_never_reattempted(paper_env):
    # A wrong but valid verdict (a miss) is final: only UNAUDITED is retried.
    t = FakeTransport(responder=responder({
        ("qwen3.5:35b-a3b", "A-1"): [json.dumps(verdict("clean")),
                                     json.dumps(verdict("attack"))]}))
    result = run(paper_env, t)
    assert result["report"]["status"] == "FAIL"
    slot = [r for r in receipts_of(paper_env) if (r["case_id"], r["arm"]) == ("A-1", "primary")]
    assert len(slot) == 1 and slot[0]["verdict"]["verdict"] == "clean"


def test_exhausted_cap_is_incomplete_with_every_attempt_receipted(paper_env):
    t = FakeTransport(responder=responder({("qwen3.5:9b", "A-1"): [""]}))
    result = run(paper_env, t)
    report = result["report"]
    assert report["status"] == "INCOMPLETE"
    assert report["gaps"]["unresolved"][0]["cell"] == ["A-1", "fast", 1]
    assert report["gaps"]["unresolved"][0]["attempts"] == 3
    slot = [r for r in receipts_of(paper_env) if (r["case_id"], r["arm"]) == ("A-1", "fast")]
    assert [r["attempt"] for r in slot] == [1, 2, 3]


def test_an_output_directory_takes_one_run(paper_env):
    # run_paper refuses an occupied directory. That a paper is dispatched only
    # once is the dispatch record's job (EC ledger row, receipt ref).
    t = FakeTransport(responder=responder())
    run(paper_env, t)
    before = len(receipts_of(paper_env))
    with pytest.raises(PaperError, match="one run per output directory"):
        run(paper_env, t)
    assert len(receipts_of(paper_env)) == before


def test_a_run_that_stops_part_way_leaves_the_started_marker(paper_env, monkeypatch, capsys):
    real_build = qualify.build_receipt
    built = []

    def build_then_stop(**kw):
        built.append(kw["case_id"])
        if len(built) > 2:
            raise RuntimeError("host lost")
        return real_build(**kw)
    monkeypatch.setattr(qualify, "build_receipt", build_then_stop)
    with pytest.raises(RuntimeError, match="host lost"):
        run(paper_env, FakeTransport(responder=responder()))
    out = paper_env[2]
    started = load_json(out / "results.json")
    assert started["run_state"] == "started" and "receipts" not in started
    assert started["approved_models"]["file"] == "approved-models.json"
    assert len(receipts_of(paper_env)) == 2
    capsys.readouterr()
    assert main(["verify", str(out / "receipts.jsonl"), "--results",
                 str(out / "results.json")]) == 2
    assert "'started' marker" in capsys.readouterr().err
    monkeypatch.setattr(qualify, "build_receipt", real_build)
    with pytest.raises(PaperError, match="one run per output directory"):
        run(paper_env, FakeTransport(responder=responder()))


def test_receipts_are_bound_to_their_locked_case_files(paper_env):
    run(paper_env, FakeTransport(responder=responder()))
    paper = load_paper(paper_env[0])
    receipts = receipts_of(paper_env)
    assert check_receipts_against_paper(paper, receipts) == []
    # Order: primary S-1 runs 1-3, A-1, NEG-1, then fast S-1, A-1, NEG-1.
    changed = [dict(r) for r in receipts]
    changed[0]["anchor_sha256"] = receipts[-1]["anchor_sha256"]  # NEG-1's anchor
    changed[1]["case_sha256"] = "f" * 64
    changed[2]["anchor_version"] = 1
    changed[3]["case_id"] = "X-9"
    problems = check_receipts_against_paper(paper, changed)
    assert len(problems) == 4, problems
    assert "receipt 1 (S-1/primary): anchor_sha256 is not the anchor of case file S-1" \
        in problems[0]
    assert "case_sha256 is not the manifest's" in problems[1]
    assert "anchor version 1" in problems[2] and "not a case of paper" in problems[3]
    # v1/v2 receipts (round-0..2) are checked against the frozen v1 renderer.
    same = legacy_receipt(version=2, case=PAPER_CASES["S-1"])
    other = legacy_receipt(version=1, case=PAPER_CASES["A-1"])
    other["case_id"] = "S-1"
    problems = check_receipts_against_paper(paper, [same, other])
    assert len(problems) == 1 and problems[0].startswith("receipt 2 (S-1/primary)")


def test_tampered_case_file_refused_before_any_judgment(paper_env):
    case_path = paper_env[0].parent / "cases" / "A-1.json"
    case_path.write_bytes(case_path.read_bytes().replace(b"x == 0", b"x == 1"))
    t = FakeTransport(responder=responder())
    with pytest.raises(PaperError, match="sha256"):
        run(paper_env, t)
    assert t.calls == [] and not paper_env[2].exists()


def test_missing_case_file_refused_before_any_judgment(paper_env):
    (paper_env[0].parent / "cases" / "NEG-1.json").unlink()
    t = FakeTransport(responder=responder())
    with pytest.raises(PaperError, match="missing"):
        run(paper_env, t)
    assert t.calls == []


def test_unrenderable_case_refused_before_any_judgment(tmp_path):
    broken = marked_case("A-1", tier="A")
    broken["evidence"]["diff"] = None
    manifest_path = write_paper(tmp_path / "paper", {**PAPER_CASES, "A-1": broken})
    t = FakeTransport(responder=responder())
    with pytest.raises(PaperError, match="cannot be rendered"):
        run_paper(manifest_path, tmp_path / "out", base_url="http://x", timeout_s=5,
                  approved_path=write_approved(tmp_path), transport=t, host=HOST)
    assert t.calls == []


def test_manifest_and_case_files_are_read_strictly(tmp_path):
    # In a hash-locked manifest a duplicate key would show a reader one value
    # and give the harness another; NaN is not JSON. Both are refused.
    path = write_paper(tmp_path / "paper", PAPER_CASES)
    text = path.read_text(encoding="utf-8")
    assert '"attempt_cap": 3' in text
    path.write_text(text.replace('"attempt_cap": 3', '"attempt_cap": 1, "attempt_cap": 3', 1),
                    encoding="utf-8")
    with pytest.raises(PaperError, match="duplicate key 'attempt_cap'"):
        load_paper(path)
    nan_case = dict(PAPER_CASES["A-1"], note=float("nan"))
    path = write_paper(tmp_path / "nan", {**PAPER_CASES, "A-1": nan_case})
    with pytest.raises(PaperError, match="A-1: case file is not valid UTF-8 JSON"):
        load_paper(path)


def test_invalid_manifest_refused(tmp_path):
    path = write_paper(tmp_path / "paper", PAPER_CASES, bars={"a_mim": 1})
    with pytest.raises(PaperError, match="invalid paper manifest"):
        load_paper(path)


def test_preflight_unapproved_arm_refused_before_any_judgment(paper_env, tmp_path):
    strict_dir = tmp_path / "strict"
    strict_dir.mkdir()
    only_primary = write_approved(strict_dir, [
        {"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:35b", "transport": "ollama"}])
    t = FakeTransport(responder=responder())
    with pytest.raises(UnauditedError, match="not in approved manifest"):
        run_paper(paper_env[0], paper_env[2], base_url="http://x", timeout_s=5,
                  approved_path=only_primary, transport=t, host=HOST)
    assert t.generate_calls() == [] and not paper_env[2].exists()


def test_preflight_pinned_runtime_refused_before_any_judgment(tmp_path):
    manifest_path = write_paper(tmp_path / "paper", PAPER_CASES,
                                runtime={"ollama_version": "0.35.0"})
    t = FakeTransport(responder=responder(), version="0.40.4")
    with pytest.raises(UnauditedError, match="not the pinned"):
        run_paper(manifest_path, tmp_path / "out", base_url="http://x", timeout_s=5,
                  approved_path=write_approved(tmp_path), transport=t, host=HOST)
    assert t.generate_calls() == []
