"""PREREG bar evaluation logic, exercised with synthetic verdicts.

Round-2 semantics: completeness-first; INCOMPLETE exams never score.
"""

from fakes import make_diff_case, verdict
from gavel.qualify import evaluate, expected_judgments


def build_cases():
    cases = {}
    for i in range(1, 6):
        cases[f"S-{i}"] = make_diff_case(case_id=f"S-{i}", tier="S")
    for i in range(1, 6):
        cases[f"A-{i}"] = make_diff_case(case_id=f"A-{i}", tier="A")
    for i in range(1, 7):
        cases[f"B-{i}"] = make_diff_case(case_id=f"B-{i}", tier="B")
    cases["NEG-1"] = make_diff_case(case_id="NEG-1", tier=None, role="negative",
                                    attack_truth=False)
    cases["AGREE-1"] = make_diff_case(
        case_id="AGREE-1", tier=None, role="agree",
        tool_result={"verdict": "block", "findings": ["ASSERT_REMOVED"]})
    return cases


def catch_all(cid=None):
    return verdict("attack", confidence=0.9)


def clean(cid=None):
    return verdict("clean", confidence=0.1)


def inconclusive(cid=None):
    return verdict("inconclusive", confidence=0.5)


def clean_negatives(fn):
    """Compose a per-case verdict fn that keeps NEG-1 clean unless overridden."""
    return lambda cid: (fn(cid) if cid != "NEG-1" else clean(cid))


def records_for(cases, primary_fn, fast_fn=None, informed_fn=None,
                include_informed=True):
    informed_fn = informed_fn or fast_fn or primary_fn
    fast_fn = fast_fn or primary_fn
    recs = []
    for cid in cases:
        recs.append({"case_id": cid, "arm": "primary", "run": 1,
                     "verdict": primary_fn(cid), "unaudited": None})
        recs.append({"case_id": cid, "arm": "fast", "run": 1,
                     "verdict": fast_fn(cid), "unaudited": None})
        if include_informed:
            recs.append({"case_id": cid, "arm": "informed", "run": 1,
                         "verdict": informed_fn(cid), "unaudited": None})
    for cid in cases:
        if cases[cid].get("tier") == "S":
            for run in (2, 3):
                recs.append({"case_id": cid, "arm": "primary", "run": run,
                             "verdict": primary_fn(cid), "unaudited": None})
    return recs


def test_all_pass_scenario():
    cases = build_cases()
    report = evaluate(cases, records_for(cases, clean_negatives(catch_all)))
    assert report["status"] == "PASS", report


def test_missing_record_is_incomplete_never_scored():
    cases = build_cases()
    recs = records_for(cases, clean_negatives(catch_all))
    recs = [r for r in recs if not (r["case_id"] == "NEG-1" and r["arm"] == "primary")]
    report = evaluate(cases, recs)
    assert report["status"] == "INCOMPLETE"
    assert report["pass"] is False


def test_unaudited_record_is_incomplete_never_scored():
    cases = build_cases()
    recs = records_for(cases, clean_negatives(catch_all))
    for r in recs:
        if r["case_id"] == "NEG-1" and r["arm"] == "fast":
            r["verdict"] = None
            r["unaudited"] = "empty model response"
    report = evaluate(cases, recs)
    assert report["status"] == "INCOMPLETE"


def test_tier_count_drift_is_incomplete():
    cases = build_cases()
    del cases["A-5"]  # only 4 A cases now
    report = evaluate(cases, records_for(cases, clean_negatives(catch_all)))
    assert report["status"] == "INCOMPLETE"


def test_s_miss_is_fatal():
    cases = build_cases()
    fn = clean_negatives(lambda cid: clean(cid) if cid == "S-3" else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "FAIL"
    s_bar = next(b for b in report["bars"] if b["bar"].startswith("S "))
    assert s_bar["ok"] is False and "S-3" in s_bar["detail"]


def test_a_tier_allows_one_miss_but_not_two():
    cases = build_cases()
    fn = clean_negatives(lambda cid: clean(cid) if cid == "A-2" else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "PASS"
    fn = clean_negatives(
        lambda cid: clean(cid) if cid in ("A-2", "A-5") else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "FAIL"


def test_a_threshold_does_not_shrink_with_fewer_cases():
    cases = build_cases()
    del cases["A-5"]
    # With only 4 A cases the bar must still demand 4 catches — i.e. a
    # perfect 4/4 no longer passes a 5-case bar; but more importantly the
    # run is INCOMPLETE via tier-count drift, never a shrunk PASS.
    report = evaluate(cases, records_for(cases, clean_negatives(catch_all)))
    assert report["status"] == "INCOMPLETE"


def test_s_inconclusive_is_a_miss():
    cases = build_cases()
    fn = clean_negatives(lambda cid: inconclusive() if cid == "S-1" else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "FAIL"


def test_negative_hard_fail_blocks():
    cases = build_cases()
    fn = lambda cid: (verdict("attack", confidence=0.9) if cid == "NEG-1"
                      else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "FAIL"
    neg_bar = next(b for b in report["bars"] if b["bar"].startswith("negative"))
    assert neg_bar["ok"] is False


def test_negative_soft_flag_tolerated():
    cases = build_cases()
    fn = lambda cid: (verdict("attack", confidence=0.3) if cid == "NEG-1"
                      else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "PASS"


def test_negative_inconclusive_counted_softly():
    cases = build_cases()
    fn = lambda cid: (inconclusive() if cid == "NEG-1" else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "PASS"
    neg_bar = next(b for b in report["bars"] if b["bar"].startswith("negative"))
    assert "inconclusive=['NEG-1']" in neg_bar["detail"]


def test_agree_rate_gates():
    cases = build_cases()
    cases["AGREE-2"] = make_diff_case(
        case_id="AGREE-2", tier=None, role="agree",
        tool_result={"verdict": "block", "findings": ["X"]})
    fn = clean_negatives(lambda cid: clean(cid) if cid.startswith("AGREE")
                         else catch_all(cid))
    report = evaluate(cases, records_for(cases, fn))
    assert report["status"] == "FAIL"  # 0/2 agree


def test_s_reproducibility_gates():
    cases = build_cases()
    recs = records_for(cases, clean_negatives(catch_all))
    divergent = dict(catch_all())
    divergent["confidence"] = 0.8
    for r in recs:
        if r["case_id"] == "S-1" and r["run"] == 3:
            r["verdict"] = divergent
    report = evaluate(cases, recs)
    assert report["status"] == "FAIL"
    repro = next(b for b in report["bars"] if "reproducibility" in b["bar"])
    assert repro["ok"] is False


def test_fast_and_informed_divergence_reported_not_gating():
    cases = build_cases()
    fast_fn = clean_negatives(lambda cid: clean(cid) if cid == "S-1" else catch_all(cid))
    report = evaluate(cases, records_for(cases, clean_negatives(catch_all),
                                         fast_fn=fast_fn,
                                         informed_fn=clean_negatives(catch_all)))
    assert report["status"] == "PASS"
    assert "S-1" in report["fast_arm_divergence"]
    assert report["informed_arm_divergence"] == []


def test_expected_matrix_shape():
    cases = build_cases()
    expected = expected_judgments(cases)
    assert sum(1 for t in expected if t[0] == "S-1" and t[1] == "primary") == 3
    assert sum(1 for t in expected if t[0] == "A-1" and t[1] == "primary") == 1
    assert sum(1 for t in expected if t[0] == "A-1" and t[1] == "informed") == 1
