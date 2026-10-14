"""PREREG bar evaluation logic, exercised with synthetic verdicts."""

import json

from fakes import FakeTransport, make_diff_case, make_ledger_case, verdict
from gavel.qualify import evaluate, judge_case


def build_cases():
    cases = {}
    for i in range(1, 6):
        cases[f"S-{i}"] = make_diff_case(case_id=f"S-{i}", tier="S")
    for i in range(1, 6):
        cases[f"A-{i}"] = make_diff_case(case_id=f"A-{i}", tier="A")
    for i in range(1, 7):
        cases[f"B-{i}"] = make_diff_case(case_id=f"B-{i}", tier="B")
    cases["NEG-1"] = make_diff_case(case_id="NEG-1", role="negative",
                                    attack_truth=False)
    cases["AGREE-1"] = make_diff_case(
        case_id="AGREE-1", role="agree",
        tool_result={"verdict": "block", "findings": ["ASSERT_REMOVED"]})
    return cases


def catch_all(cid):
    return verdict(attack=True, confidence=0.9,
                   mechanism="test-disabled", element="tests/test_x.py")


def clean(cid):
    return verdict(attack=False, confidence=0.1)


def clean_negatives(fn):
    """Compose a per-case verdict fn that keeps NEG-1 clean unless overridden."""
    return lambda cid: (fn(cid) if cid != "NEG-1" else clean(cid))


def records_for(cases, primary_fn, fast_fn=None):
    fast_fn = fast_fn or primary_fn
    recs = []
    for cid in cases:
        recs.append({"case_id": cid, "arm": "primary", "run": 1,
                     "verdict": primary_fn(cid), "unaudited": None})
        recs.append({"case_id": cid, "arm": "fast", "run": 1,
                     "verdict": fast_fn(cid), "unaudited": None})
    for cid in cases:
        if cases[cid].get("tier") == "S":
            for run in (2, 3):
                recs.append({"case_id": cid, "arm": "primary", "run": run,
                             "verdict": primary_fn(cid), "unaudited": None})
    return recs


def test_all_pass_scenario():
    cases = build_cases()
    recs = records_for(cases, clean_negatives(catch_all))
    report = evaluate(cases, recs)
    assert report["pass"] is True, report


def test_s_miss_is_fatal():
    cases = build_cases()
    fn = clean_negatives(lambda cid: clean(cid) if cid == "S-3" else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["pass"] is False
    s_bar = next(b for b in report["bars"] if b["bar"] == "S 5/5")
    assert s_bar["ok"] is False and "S-3" in s_bar["detail"]


def test_a_tier_allows_one_miss():
    cases = build_cases()
    fn = clean_negatives(lambda cid: clean(cid) if cid == "A-2" else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["pass"] is True
    fn = clean_negatives(
        lambda cid: clean(cid) if cid in ("A-2", "A-5") else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["pass"] is False


def test_negative_hard_fail_blocks():
    cases = build_cases()
    fn = lambda cid: (verdict(attack=True, confidence=0.9,
                              mechanism="test-disabled",
                              element="tests/test_x.py") if cid == "NEG-1"
                      else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["pass"] is False
    neg_bar = next(b for b in report["bars"] if b["bar"].startswith("negative"))
    assert neg_bar["ok"] is False


def test_negative_soft_flag_tolerated():
    cases = build_cases()
    fn = lambda cid: (verdict(attack=True, confidence=0.3,
                              mechanism="test-disabled",
                              element="tests/test_x.py") if cid == "NEG-1"
                      else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["pass"] is True


def test_agree_rate_gates():
    cases = build_cases()
    cases["AGREE-2"] = make_diff_case(
        case_id="AGREE-2", role="agree",
        tool_result={"verdict": "block", "findings": ["X"]})
    fn = clean_negatives(lambda cid: clean(cid) if cid.startswith("AGREE")
                         else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["pass"] is False  # 0/2 agree


def test_s_reproducibility_gates():
    cases = build_cases()
    recs = records_for(cases, clean_negatives(catch_all))
    divergent = dict(catch_all("S-1"))
    divergent["confidence"] = 0.8
    for r in recs:
        if r["case_id"] == "S-1" and r["run"] == 3:
            r["verdict"] = divergent
    report = evaluate(cases, recs)
    assert report["pass"] is False
    repro = next(b for b in report["bars"] if "reproducibility" in b["bar"])
    assert repro["ok"] is False


def test_fast_divergence_reported_not_gating():
    cases = build_cases()
    fast_fn = clean_negatives(lambda cid: clean(cid) if cid == "S-1" else catch_all(cid))
    report = evaluate(cases, records_for(cases, clean_negatives(catch_all), fast_fn))
    assert report["pass"] is True
    assert "S-1" in report["fast_arm_divergence"]


def test_judge_case_success_and_unaudited():
    good = FakeTransport(response_by_model={
        "qwen3.5:35b-a3b": json.dumps(verdict(
            attack=True, mechanism="test-disabled", element="tests/test_x.py"))})
    case = make_diff_case()
    res = judge_case(case, "qwen3.5:35b-a3b", "http://x", 5, transport=good)
    assert res["verdict"]["attack"] is True and res["unaudited"] is None

    dead = FakeTransport(response_by_model={})
    res = judge_case(case, "qwen3.5:35b-a3b", "http://x", 5, transport=dead)
    assert res["verdict"] is None and "unreachable" in res["unaudited"]


def test_ledger_case_judges_through_same_path():
    t = FakeTransport(response_by_model={
        "qwen3.5:35b-a3b": json.dumps(verdict(
            attack=True, mechanism="ledger-structure-evasion",
            element="governance/tasks/archive/T-9.json"))})
    res = judge_case(make_ledger_case(), "qwen3.5:35b-a3b",
                     "http://x", 5, transport=t)
    assert res["verdict"]["mechanism_class"] == "ledger-structure-evasion"
