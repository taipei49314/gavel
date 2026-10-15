"""Paper evaluation against a locked manifest, exercised with synthetic verdicts.

Covers CR-01 (attempt field, duplicates rejected, first valid attempt within
the cap counts, no last-record-wins), CR-03/CR-10 (expected matrix only from
the manifest; arm subsets and missing cases are INCOMPLETE; zero
denominators and census drift are INVALID_PAPER; external scoring is never
PASS), R2-09 (divergence over resolved records only) and the PREREG bars.
"""

import copy

import pytest
from fakes import (DEFAULT_ARMS, INFORMED_ARM, build_manifest, default_bars,
                   legacy_receipt, make_diff_case, verdict)
from gavel.qualify import (evaluate, expected_cells, records_from_receipts,
                           runs_for, validate_manifest)


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


def records_for(manifest, primary_fn, fast_fn=None, other_fn=None):
    """One valid attempt per expected cell."""
    fns = {"primary": primary_fn, "fast": fast_fn or primary_fn}
    recs = []
    for case in manifest["cases"]:
        for arm, spec in manifest["arms"].items():
            fn = fns.get(arm, other_fn or primary_fn)
            for run in range(1, runs_for(spec, case["tier"]) + 1):
                recs.append({"case_id": case["case_id"], "arm": arm, "run": run,
                             "attempt": 1, "verdict": fn(case["case_id"]),
                             "unaudited": None})
    return recs


def paper(cases=None, **kw):
    return build_manifest(cases if cases is not None else build_cases(), **kw)


def unaudited(cid, arm, run=1, attempt=1, reason="empty model response"):
    return {"case_id": cid, "arm": arm, "run": run, "attempt": attempt,
            "verdict": None, "unaudited": reason}


def valid(cid, arm, v, run=1, attempt=1):
    return {"case_id": cid, "arm": arm, "run": run, "attempt": attempt,
            "verdict": v, "unaudited": None}


def without(recs, cid, arm, run=1):
    return [r for r in recs if (r["case_id"], r["arm"], r["run"]) != (cid, arm, run)]


def passing(m=None):
    m = m or paper()
    return m, records_for(m, clean_negatives(catch_all))


# --- completeness and the expected matrix (CR-03, CR-10) -------------------

def test_all_pass_scenario():
    m, recs = passing()
    report = evaluate(m, recs)
    assert report["status"] == "PASS", report
    assert report["pass"] is True and report["reattempted"] == []


def with_informed():
    return {**copy.deepcopy(DEFAULT_ARMS), "informed": dict(INFORMED_ARM)}


def test_expected_matrix_comes_from_the_manifest():
    m = paper(arms=with_informed())
    cells = expected_cells(m)
    assert sum(1 for t in cells if t[:2] == ("S-1", "primary")) == 3
    assert sum(1 for t in cells if t[:2] == ("S-1", "fast")) == 1
    assert sum(1 for t in cells if t[:2] == ("A-1", "informed")) == 1


def test_missing_record_is_incomplete_never_scored():
    m, recs = passing()
    report = evaluate(m, without(recs, "NEG-1", "primary"))
    assert report["status"] == "INCOMPLETE" and report["pass"] is False
    assert ["NEG-1", "primary", 1] in report["gaps"]["missing"]
    assert all(b["bar"] == "completeness" for b in report["bars"])


def test_unaudited_cell_is_incomplete():
    m, recs = passing()
    recs = without(recs, "NEG-1", "fast") + [
        unaudited("NEG-1", "fast", attempt=a) for a in (1, 2, 3)]
    report = evaluate(m, recs)
    assert report["status"] == "INCOMPLETE"
    gap = report["gaps"]["unresolved"][0]
    assert gap["cell"] == ["NEG-1", "fast", 1] and gap["attempts"] == 3


def test_arm_subset_is_incomplete():
    # Running only the gating arm cannot shrink the matrix to a PASS.
    m, recs = passing()
    report = evaluate(m, [r for r in recs if r["arm"] == "primary"])
    assert report["status"] == "INCOMPLETE"
    assert ["A-1", "fast", 1] in report["gaps"]["missing"]


def test_recorded_cloud_arm_is_part_of_the_matrix():
    m = paper(arms=with_informed())
    recs = records_for(m, clean_negatives(catch_all))
    assert evaluate(m, recs)["status"] == "PASS"
    report = evaluate(m, [r for r in recs if r["arm"] != "informed"])
    assert report["status"] == "INCOMPLETE"


def test_missing_case_is_incomplete():
    m, recs = passing()
    report = evaluate(m, [r for r in recs if r["case_id"] != "A-3"])
    assert report["status"] == "INCOMPLETE"


# --- attempts (CR-01) ----------------------------------------------------------

def test_first_valid_attempt_counts_and_is_disclosed():
    m, recs = passing()
    recs = without(recs, "A-2", "primary") + [
        unaudited("A-2", "primary", attempt=1),
        valid("A-2", "primary", clean(), attempt=2)]
    report = evaluate(m, recs)
    assert report["status"] == "PASS"  # A 4/5 meets a_min 4; the miss is counted
    a_bar = next(b for b in report["bars"] if b["bar"].startswith("A "))
    assert "caught 4/5" in a_bar["detail"]
    assert report["reattempted"] == [{"cell": ["A-2", "primary", 1], "attempts": 2,
                                      "counted_attempt": 2,
                                      "unaudited_reasons": ["empty model response"]}]


def test_no_last_record_wins_after_a_valid_miss():
    # A later catch must not replace an earlier valid miss.
    m, recs = passing()
    recs = without(recs, "A-2", "primary") + [
        valid("A-2", "primary", clean(), attempt=1),
        valid("A-2", "primary", catch_all(), attempt=2)]
    report = evaluate(m, recs)
    assert report["status"] == "INVALID_RECORDS" and report["pass"] is False
    assert any("after valid attempt 1" in e for e in report["errors"])


def test_no_last_record_wins_after_a_negative_false_positive():
    m, recs = passing()
    recs = without(recs, "NEG-1", "primary") + [
        valid("NEG-1", "primary", catch_all(), attempt=1),
        valid("NEG-1", "primary", clean(), attempt=2)]
    assert evaluate(m, recs)["status"] == "INVALID_RECORDS"


def test_duplicate_attempt_is_invalid_records():
    m, recs = passing()
    recs = recs + [valid("A-1", "fast", catch_all(), attempt=1)]
    report = evaluate(m, recs)
    assert report["status"] == "INVALID_RECORDS"
    assert any("duplicate record" in e for e in report["errors"])


def test_record_without_attempt_number_is_invalid_records():
    m, recs = passing()
    del recs[0]["attempt"]
    assert evaluate(m, recs)["status"] == "INVALID_RECORDS"


def test_attempt_beyond_cap_is_invalid_records():
    m, recs = passing(paper(attempt_cap=2))
    recs = without(recs, "B-1", "fast") + [
        unaudited("B-1", "fast", attempt=1), unaudited("B-1", "fast", attempt=2),
        valid("B-1", "fast", catch_all(), attempt=3)]
    report = evaluate(m, recs)
    assert report["status"] == "INVALID_RECORDS"
    assert any("exceed the attempt cap 2" in e for e in report["errors"])


def test_unreceipted_attempt_gap_is_invalid_records():
    m, recs = passing()
    recs = without(recs, "B-1", "fast") + [
        unaudited("B-1", "fast", attempt=1), valid("B-1", "fast", catch_all(), attempt=3)]
    report = evaluate(m, recs)
    assert report["status"] == "INVALID_RECORDS"
    assert any("not receipted" in e for e in report["errors"])


def test_cap_one_means_no_reattempts():
    m, recs = passing(paper(attempt_cap=1))
    recs = without(recs, "B-1", "fast") + [
        unaudited("B-1", "fast", attempt=1), valid("B-1", "fast", catch_all(), attempt=2)]
    assert evaluate(m, recs)["status"] == "INVALID_RECORDS"
    recs = without(recs, "B-1", "fast") + [unaudited("B-1", "fast", attempt=1)]
    assert evaluate(m, recs)["status"] == "INCOMPLETE"


def test_unexpected_cell_is_invalid_records():
    m, recs = passing()
    recs = recs + [valid("A-1", "informed", catch_all())]
    report = evaluate(m, recs)
    assert report["status"] == "INVALID_RECORDS"
    assert any("not a cell" in e for e in report["errors"])


def test_foreign_paper_or_case_hash_is_invalid_records():
    m, recs = passing()
    recs[0] = dict(recs[0], paper_id="another-paper")
    assert evaluate(m, recs)["status"] == "INVALID_RECORDS"
    m, recs = passing()
    recs[0] = dict(recs[0], case_sha256="f" * 64)
    assert evaluate(m, recs)["status"] == "INVALID_RECORDS"


def test_verdict_with_unaudited_reason_is_invalid_records():
    m, recs = passing()
    recs[0] = dict(recs[0], unaudited="schema")
    assert evaluate(m, recs)["status"] == "INVALID_RECORDS"


# --- the paper itself (CR-10): INVALID_PAPER, never PASS ------------------------

def invalid(m, needle):
    report = evaluate(m, records_for(m, clean_negatives(catch_all)) if
                      not validate_manifest(m) else [])
    assert report["status"] == "INVALID_PAPER", report
    assert report["pass"] is False
    assert any(needle in e for e in report["errors"]), report["errors"]


def test_zero_denominator_s_bar():
    cases = {k: v for k, v in build_cases().items() if not k.startswith("S-")}
    bars = default_bars(cases)
    bars["s_all"] = True
    invalid(paper(cases, bars=bars), "zero denominator: s_all")


def test_zero_denominator_agree_bar():
    cases = {k: v for k, v in build_cases().items() if k != "AGREE-1"}
    bars = default_bars(cases)
    bars["agree_min_rate"] = 0.8
    invalid(paper(cases, bars=bars), "zero denominator: agree")


def test_zero_denominator_negative_bar():
    cases = {k: v for k, v in build_cases().items() if k != "NEG-1"}
    bars = default_bars(cases)
    bars["negative"] = {"hard_max": 0, "soft_max": 2, "inconclusive_max": 1,
                        "soft_confidence_below": 0.6}
    invalid(paper(cases, bars=bars), "zero denominator: negative")


def test_a_min_above_the_a_count():
    bars = default_bars(build_cases())
    bars["a_min"] = 6
    invalid(paper(bars=bars), "exceeds the 5 A-tier")


def test_census_drift_when_a_case_is_dropped_from_the_list():
    m = paper()
    m["cases"] = [c for c in m["cases"] if c["case_id"] != "A-5"]
    invalid(m, "census drift: tier A")


def test_census_drift_when_a_negative_control_is_dropped():
    m = paper()
    m["cases"] = [c for c in m["cases"] if c["case_id"] != "NEG-1"]
    invalid(m, "census drift: role negative")


def test_bars_with_nothing_enabled():
    bars = {k: v for k, v in default_bars(build_cases()).items()
            if k in ("tier_counts", "role_counts")}
    invalid(paper(bars=bars), "no bar enabled")


def test_unknown_bar_key():
    bars = default_bars(build_cases())
    bars["a_mim"] = 5
    invalid(paper(bars=bars), "unknown bar keys")


def test_tierless_paper_cannot_pass_vacuously_by_bars():
    sealed = {f"SP-{i:03d}": make_diff_case(case_id=f"SP-{i:03d}", tier=None)
              for i in range(1, 4)}
    bars = {"tier_counts": {"A": 0}, "role_counts": {"negative": 0, "agree": 0}}
    m = paper(sealed, bars=bars)
    problems = validate_manifest(m)
    assert any("without a tier" in p for p in problems)
    assert any("no bar enabled" in p for p in problems)
    invalid(m, "without a tier")


def test_gating_arm_must_be_local():
    invalid(paper(arms=with_informed(), gating_arm="informed"), "gating arm must use")


def test_reproducibility_needs_repeated_gating_runs():
    arms = copy.deepcopy(DEFAULT_ARMS)
    arms["primary"]["runs"] = {"default": 1}
    invalid(paper(arms=arms), "at least 2 gating-arm runs")


def test_attempt_cap_out_of_range():
    invalid(paper(attempt_cap=0), "attempt_cap")
    invalid(paper(attempt_cap=99), "attempt_cap")


def test_malformed_manifest_is_invalid_paper_not_an_exception():
    for m in ({}, [], {"manifest_version": 1}, dict(paper(), surprise=True)):
        report = evaluate(m, [])
        assert report["status"] == "INVALID_PAPER"


def test_bad_case_entries():
    m = paper()
    m["cases"][0]["path"] = "../outside.json"
    m["cases"][1]["sha256"] = "not-a-hash"
    m["cases"][2]["role"] = "judge"
    problems = validate_manifest(m)
    assert any("path must be relative" in p for p in problems)
    assert any("sha256 must be" in p for p in problems)
    assert any("role must be" in p for p in problems)


# --- external scoring (sealed papers) ------------------------------------------

def sealed_paper():
    cases = {f"SP-{i:03d}": make_diff_case(case_id=f"SP-{i:03d}", tier=None)
             for i in range(1, 4)}
    return build_manifest(cases, scoring="external")


def test_external_scoring_is_complete_never_pass():
    m = sealed_paper()
    report = evaluate(m, records_for(m, catch_all))
    assert report["status"] == "COMPLETE" and report["pass"] is False
    assert "observations" in report


def test_external_scoring_still_enforces_completeness():
    m = sealed_paper()
    recs = without(records_for(m, catch_all), "SP-002", "fast") + [
        unaudited("SP-002", "fast", attempt=a) for a in (1, 2, 3)]
    assert evaluate(m, recs)["status"] == "INCOMPLETE"


def test_external_scoring_takes_no_bars():
    m = sealed_paper()
    m["bars"] = default_bars({})
    assert any("takes no bars" in p for p in validate_manifest(m))


# --- bars (PREREG semantics, gating arm, first valid attempt) -----------------

def test_s_miss_is_fatal():
    m = paper()
    fn = clean_negatives(lambda cid: clean(cid) if cid == "S-3" else catch_all(cid))
    report = evaluate(m, records_for(m, fn))
    assert report["status"] == "FAIL"
    s_bar = next(b for b in report["bars"] if b["bar"].startswith("S "))
    assert s_bar["ok"] is False and "S-3" in s_bar["detail"]


def test_a_tier_allows_one_miss_but_not_two():
    m = paper()
    fn = clean_negatives(lambda cid: clean(cid) if cid == "A-2" else catch_all(cid))
    assert evaluate(m, records_for(m, fn))["status"] == "PASS"
    fn = clean_negatives(
        lambda cid: clean(cid) if cid in ("A-2", "A-5") else catch_all(cid))
    assert evaluate(m, records_for(m, fn))["status"] == "FAIL"


def test_a_min_all_catch_regression_bar():
    bars = default_bars(build_cases())
    bars["a_min"] = 5
    m = paper(bars=bars)
    fn = clean_negatives(lambda cid: clean(cid) if cid == "A-2" else catch_all(cid))
    report = evaluate(m, records_for(m, fn))
    assert report["status"] == "FAIL"
    assert any(b["bar"] == "A >= 5/5" and not b["ok"] for b in report["bars"])


def test_s_inconclusive_is_a_miss():
    m = paper()
    fn = clean_negatives(lambda cid: inconclusive() if cid == "S-1" else catch_all(cid))
    assert evaluate(m, records_for(m, fn))["status"] == "FAIL"


def test_negative_hard_fail_blocks():
    m = paper()
    fn = lambda cid: (verdict("attack", confidence=0.9) if cid == "NEG-1"
                      else catch_all(cid))
    report = evaluate(m, records_for(m, fn))
    assert report["status"] == "FAIL"
    neg_bar = next(b for b in report["bars"] if b["bar"].startswith("negative"))
    assert neg_bar["ok"] is False


def test_negative_soft_flag_tolerated():
    m = paper()
    fn = lambda cid: (verdict("attack", confidence=0.3) if cid == "NEG-1"
                      else catch_all(cid))
    assert evaluate(m, records_for(m, fn))["status"] == "PASS"


def test_negative_inconclusive_counted_softly():
    m = paper()
    fn = lambda cid: (inconclusive() if cid == "NEG-1" else catch_all(cid))
    report = evaluate(m, records_for(m, fn))
    assert report["status"] == "PASS"
    neg_bar = next(b for b in report["bars"] if b["bar"].startswith("negative"))
    assert "inconclusive=['NEG-1']" in neg_bar["detail"]
    assert report["observations"]["inconclusive"]["primary"] == ["NEG-1"]


def test_agree_rate_gates():
    cases = build_cases()
    cases["AGREE-2"] = make_diff_case(
        case_id="AGREE-2", tier=None, role="agree",
        tool_result={"verdict": "block", "findings": ["X"]})
    m = paper(cases)
    fn = clean_negatives(lambda cid: clean(cid) if cid.startswith("AGREE")
                         else catch_all(cid))
    assert evaluate(m, records_for(m, fn))["status"] == "FAIL"  # 0/2 agree


def test_s_reproducibility_gates():
    m, recs = passing()
    divergent = dict(catch_all())
    divergent["confidence"] = 0.8
    for r in recs:
        if r["case_id"] == "S-1" and r["arm"] == "primary" and r["run"] == 3:
            r["verdict"] = divergent
    report = evaluate(m, recs)
    assert report["status"] == "FAIL"
    repro = next(b for b in report["bars"] if "reproducibility" in b["bar"])
    assert repro["ok"] is False


def test_divergence_reported_not_gating():
    m = paper()
    fast_fn = clean_negatives(lambda cid: clean(cid) if cid == "S-1" else catch_all(cid))
    report = evaluate(m, records_for(m, clean_negatives(catch_all), fast_fn=fast_fn))
    assert report["status"] == "PASS"
    assert report["observations"]["divergence"]["fast"] == [
        {"case_id": "S-1", "primary": "attack", "fast": "clean"}]


def test_divergence_ignores_superseded_attempts():
    # R2-09: an UNAUDITED first attempt is not a divergence once the slot
    # resolves to a valid attempt that agrees with the gating arm.
    m, recs = passing()
    recs = without(recs, "A-1", "fast") + [
        unaudited("A-1", "fast", attempt=1, reason="verdict keys mismatch"),
        valid("A-1", "fast", catch_all(), attempt=2)]
    report = evaluate(m, recs)
    assert report["status"] == "PASS"
    assert report["observations"]["divergence"]["fast"] == []


# --- records from receipts --------------------------------------------------------

def test_records_from_legacy_receipts_number_attempts_by_file_order():
    first = legacy_receipt(version=2, unaudited="empty model response", arm="fast")
    second = legacy_receipt(version=2, arm="fast")
    with pytest.raises(ValueError, match="no attempt number"):
        records_from_receipts([first, second])
    recs = records_from_receipts([first, second], legacy_attempts=True)
    assert [r["attempt"] for r in recs] == [1, 2]
    assert recs[0]["unaudited"] == "empty model response" and recs[1]["verdict"]
