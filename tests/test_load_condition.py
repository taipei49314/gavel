"""Load condition "fresh" (round-3 decision 4a(i), 2026-10-16): every local
judgment runs on a freshly loaded model with an empty prompt cache. Before
each judgment every model the daemon lists is unloaded and /api/ps must list
none; the judgment's generate call carries keep_alive 0; the receipt records
both, content verification refuses a valid verdict recorded otherwise, and a
paper whose manifest sets the condition refuses receipts judged without it.
"""

import json
import urllib.error

import pytest
from fakes import (FakeTransport, build_manifest, fake_judgment, make_diff_case,
                   marked_case, marker, verdict, write_approved, write_paper)
from gavel import judge
from gavel.judge import UnauditedError, generate, loaded_models, unload_all
from gavel.prompt import MECHANISM_CLASSES
from gavel.qualify import (check_receipts_against_paper, judge_case, load_paper,
                           run_paper, validate_manifest)
from gavel.receipts import ReceiptLog, build_receipt, verify_file

PRIMARY = "qwen3.5:35b-a3b"
FAST = "qwen3.5:9b"
HOST = {"hostname": "pool-host-1", "node": "pool-host-1", "system": "Windows",
        "python": "3.12.10"}


class FakeClock:
    """A monotonic clock that only moves when the code under test sleeps."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def approved(tmp_path):
    return write_approved(tmp_path)


@pytest.fixture(autouse=True)
def no_poll_wait(monkeypatch):
    monkeypatch.setattr(judge, "FRESH_UNLOAD_POLL_S", 0)


def attack_transport(**kw):
    return FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("attack")),
                                            FAST: json.dumps(verdict("clean"))}, **kw)


# --- /api/ps and unloading -------------------------------------------------

def test_loaded_models_lists_names_sorted():
    t = FakeTransport(loaded=[PRIMARY, FAST])
    assert loaded_models("http://x", transport=t) == sorted([PRIMARY, FAST])


@pytest.mark.parametrize("response", [None, [], {"models": None}, {"models": [{"size": 1}]},
                                      {"models": [{"name": ""}]}])
def test_loaded_models_malformed_answer_is_unaudited(response):
    with pytest.raises(UnauditedError, match="malformed /api/ps"):
        loaded_models("http://x", transport=lambda *a, **k: response)


def test_loaded_models_daemon_down_is_unaudited():
    t = FakeTransport(ps_error=urllib.error.URLError("refused"))
    with pytest.raises(UnauditedError, match="listing loaded models"):
        loaded_models("http://x", transport=t)


def test_unload_all_unloads_every_listed_model_and_waits_for_the_daemon():
    clock = FakeClock()
    t = FakeTransport(loaded=[PRIMARY, FAST], unload_lag=2)
    before = unload_all("http://x", transport=t, wait_s=10, poll_s=0.5,
                        sleep=clock.sleep, clock=clock)
    assert before == sorted([PRIMARY, FAST])
    assert [c[2] for c in t.unload_calls()] == [{"model": m, "keep_alive": 0}
                                                for m in sorted([PRIMARY, FAST])]
    assert clock.sleeps == [0.5, 0.5]  # listed twice more while unloading
    assert loaded_models("http://x", transport=t) == []
    assert t.generate_calls() == []  # nothing was judged or loaded


def test_unload_all_with_nothing_loaded_sends_nothing():
    t = FakeTransport()
    assert unload_all("http://x", transport=t, sleep=pytest.fail) == []
    assert t.unload_calls() == []


def test_unload_all_refuses_a_model_that_stays_loaded():
    clock = FakeClock()
    t = FakeTransport(loaded=[FAST], sticky=[FAST])
    with pytest.raises(UnauditedError, match="still loaded 3 s"):
        unload_all("http://x", transport=t, wait_s=3, poll_s=1, sleep=clock.sleep, clock=clock)
    assert clock.now == 3


def test_unload_request_failure_is_unaudited():
    def transport(method, url, payload=None, timeout=30):
        if "/api/ps" in url:
            return {"models": [{"name": FAST}]}
        raise urllib.error.URLError("refused")
    with pytest.raises(UnauditedError, match="unload request for qwen3.5:9b failed"):
        unload_all("http://x", transport=transport)


# --- generate --------------------------------------------------------------

def test_generate_sends_keep_alive_only_when_given():
    t = attack_transport(extra={"load_duration": 31_000_000_000})
    generate(PRIMARY, "prompt", "http://x", 5, transport=t)
    out = generate(PRIMARY, "prompt", "http://x", 5, transport=t, keep_alive=0)
    first, second = (c[2] for c in t.generate_calls())
    assert "keep_alive" not in first and second["keep_alive"] == 0
    assert out["generation"]["load_duration"] == 31_000_000_000


# --- judge_case --------------------------------------------------------------

def test_fresh_judgment_unloads_first_and_records_the_condition(approved):
    t = attack_transport(loaded=[FAST])
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved, load_condition="fresh")
    assert res["unaudited"] is None and res["verdict"]["verdict"] == "attack"
    assert res["execution"] == {"base_url": "http://x", "timeout_s": 5,
                                "load_condition": "fresh", "keep_alive": 0,
                                "loaded_before_unload": [FAST], "loaded_before_call": []}
    unload_at = t.calls.index(t.unload_calls()[0])
    judged_at = t.calls.index(t.generate_calls()[0])
    assert unload_at < judged_at
    assert t.generate_calls()[0][2]["keep_alive"] == 0
    # The judged model was unloaded once it answered.
    assert loaded_models("http://x", transport=t) == []


def test_fresh_judgments_in_a_row_each_start_from_no_loaded_model(approved):
    t = attack_transport(unload_lag=3)
    for _ in range(3):
        res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                         approved_models=approved, load_condition="fresh")
        assert res["unaudited"] is None
        assert res["execution"]["loaded_before_call"] == []
    assert len(t.generate_calls()) == 3


def test_fresh_judgment_with_a_model_that_stays_loaded_is_unaudited(approved, monkeypatch):
    monkeypatch.setattr(judge, "FRESH_UNLOAD_WAIT_S", 0)
    t = attack_transport(loaded=[FAST], sticky=[FAST])
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved, load_condition="fresh")
    assert res["verdict"] is None and "still loaded" in res["unaudited"]
    assert t.generate_calls() == []  # never judged on a loaded daemon


def test_fresh_judgment_without_api_ps_is_unaudited(approved):
    t = attack_transport(ps_error=urllib.error.URLError("refused"))
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved, load_condition="fresh")
    assert res["verdict"] is None and "listing loaded models" in res["unaudited"]
    assert t.generate_calls() == []


def test_unknown_load_condition_is_unaudited(approved):
    t = attack_transport()
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved, load_condition="warm")
    assert res["verdict"] is None and "unknown load condition" in res["unaudited"]
    assert t.generate_calls() == []


def test_without_a_load_condition_nothing_is_unloaded(approved):
    t = attack_transport(loaded=[FAST])
    res = judge_case(make_diff_case(), PRIMARY, "http://x", 5, transport=t,
                     approved_models=approved)
    assert res["unaudited"] is None
    assert res["execution"] == {"base_url": "http://x", "timeout_s": 5}
    assert t.unload_calls() == [] and "keep_alive" not in t.generate_calls()[0][2]


def test_cloud_transport_ignores_the_load_condition(approved):
    def fake_agy(model, prompt, base_url, timeout_s, transport=None, options=None):
        return {"raw": json.dumps(verdict("clean")), "generation": {"exit_code": 0}}

    res = judge_case(make_diff_case(), "gemini-4-argon-high", "", 5,
                     approved_models=approved, generate_fn=fake_agy, transport_name="agy",
                     load_condition="fresh")
    assert res["unaudited"] is None and res["execution"] == {"timeout_s": 5}


# --- manifest, run_paper and the paper binding ---------------------------------

PAPER_CASES = {
    "S-1": marked_case("S-1", tier="S"),
    "A-1": marked_case("A-1", tier="A"),
    "NEG-1": marked_case("NEG-1", tier=None, role="negative", attack_truth=False),
}


def test_manifest_load_condition_is_validated():
    assert validate_manifest(build_manifest(PAPER_CASES, load_condition="fresh")) == []
    assert "load_condition must be one of ['fresh']" in \
        validate_manifest(build_manifest(PAPER_CASES, load_condition="warm"))


def respond(model, prompt):
    cid = next(c for c in PAPER_CASES if marker(c) in prompt)
    return json.dumps(verdict("clean" if cid == "NEG-1" else "attack"))


def test_fresh_paper_judges_every_cell_on_a_freshly_loaded_model(tmp_path):
    manifest_path = write_paper(tmp_path / "paper", PAPER_CASES, load_condition="fresh")
    approved = write_approved(tmp_path)
    t = FakeTransport(responder=respond, loaded=[PRIMARY], unload_lag=1)
    result = run_paper(manifest_path, tmp_path / "out", base_url="http://x", timeout_s=5,
                       approved_path=approved, transport=t, host=HOST)
    assert result["report"]["status"] == "PASS", result["report"]
    receipts = verify_file(tmp_path / "out" / "receipts.jsonl", MECHANISM_CLASSES, content=True)
    assert len(receipts) == 8
    assert all(r["execution"]["load_condition"] == "fresh" and r["execution"]["keep_alive"] == 0
               and r["execution"]["loaded_before_call"] == [] for r in receipts)
    # Each primary judgment found a primary model still listed (before the
    # paper: the one already loaded; later: the one the previous judgment had
    # just used, still unloading) and unloaded it before judging.
    assert [r["arm"] for r in receipts[:5]] == ["primary"] * 5
    assert all(r["execution"]["loaded_before_unload"] == [PRIMARY] for r in receipts[:5])
    assert all(c[2]["keep_alive"] == 0 for c in t.generate_calls())
    assert check_receipts_against_paper(load_paper(manifest_path), receipts) == []


def test_paper_with_a_load_condition_refuses_receipts_judged_without_it(tmp_path):
    manifest_path = write_paper(tmp_path / "paper", PAPER_CASES)
    approved = write_approved(tmp_path)
    run_paper(manifest_path, tmp_path / "out", base_url="http://x", timeout_s=5,
              approved_path=approved, transport=FakeTransport(responder=respond), host=HOST)
    receipts = verify_file(tmp_path / "out" / "receipts.jsonl", MECHANISM_CLASSES, content=True)
    fresh_path = write_paper(tmp_path / "fresh", PAPER_CASES, load_condition="fresh")
    problems = check_receipts_against_paper(load_paper(fresh_path), receipts)
    assert len(problems) == len(receipts)
    assert all("not judged under the paper's load condition 'fresh'" in p for p in problems)


# --- receipt content verification --------------------------------------------------

def _receipt(tmp_path, execution, **kw):
    judgment = fake_judgment(**kw)
    judgment["execution"] = dict(judgment["execution"], **execution)
    path = tmp_path / "receipts.jsonl"
    ReceiptLog(path).append(build_receipt(case_id="T-1", arm="primary", run=1, attempt=1,
                                          judgment=judgment, host=HOST))
    return path


FRESH = {"load_condition": "fresh", "keep_alive": 0, "loaded_before_unload": [],
         "loaded_before_call": []}


def test_fresh_receipt_verifies(tmp_path):
    rec = verify_file(_receipt(tmp_path, FRESH), MECHANISM_CLASSES, content=True)[0]
    assert rec["execution"]["load_condition"] == "fresh"


@pytest.mark.parametrize("change, message", [
    ({"loaded_before_call": [PRIMARY]}, "empty model list"),
    ({"loaded_before_call": None}, "empty model list"),
    ({"keep_alive": None}, "keep_alive 0"),
    ({"load_condition": "warm"}, "unknown load condition"),
])
def test_valid_verdict_not_judged_fresh_is_refused(tmp_path, change, message):
    path = _receipt(tmp_path, dict(FRESH, **change))
    verify_file(path)  # structurally fine
    with pytest.raises(ValueError, match=message):
        verify_file(path, MECHANISM_CLASSES, content=True)


def test_unaudited_fresh_receipt_needs_no_empty_list(tmp_path):
    path = _receipt(tmp_path, dict(FRESH, loaded_before_call=[FAST]),
                    unaudited="models loaded before a fresh-load judgment", generation={})
    assert verify_file(path, MECHANISM_CLASSES, content=True)[0]["verdict"] is None
