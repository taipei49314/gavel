"""The single judgment path (judge_case) shared by exam and scan.

Covers CR-02/F4 (approved-models checked on every judgment, default path
not CWD), the digest and runtime version read before and after each
judgment, CR-07 (raw output kept on UNAUDITED), CR-14 (transport errors are
UNAUDITED, never an exception), CR-16 (truncation guard, options recorded)
and GOV-12 (execution facts per transport).
"""

import json
import urllib.error

import pytest
from fakes import (FakeTransport, fake_judgment, make_diff_case,
                   make_ledger_case, raising, verdict, write_approved)
from gavel.anchor import ANCHOR_VERSION
from gavel.judge import DEFAULT_NUM_CTX, SCHEMA_VERSION
from gavel.prompt import PROMPT_VERSION
from gavel.qualify import judge_case

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
