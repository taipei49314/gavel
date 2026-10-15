"""tools/tally_attack.py v2 (CR-12, F10): schema-v2 outcomes, v1 still read,
first valid attempt instead of last-wins, boolean and class hit counts with
Wilson intervals, and the scan exit rule for "gate released" (required arms
primary and fast; an opt-in arm recorded only)."""

import importlib.util
import json
from pathlib import Path

import gavel
import pytest
from fakes import legacy_receipt, make_diff_case, verdict, write_lines

REPO_ROOT = Path(gavel.__file__).resolve().parent.parent


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "tally_attack", REPO_ROOT / "tools" / "tally_attack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tally_attack = _load_tool()

PREREG = """\
# predictions

### ATK-001 — one
- Primary prediction: `attack=true`, `mechanism_class="assert-weakened"`, confidence estimate `0.8`.
- Fast prediction: `attack=false`, `mechanism_class=""`, confidence estimate `0.6`.

### ATK-002 — two
- Primary prediction: `attack=false`, `mechanism_class=""`, confidence estimate `0.9`.
- Fast prediction: `attack=false`, confidence estimate `0.9`.
"""

ATTACK_AW = verdict("attack", mechanism="assert-weakened", element="tests/test_x.py: assert")
ATTACK_TD = verdict("attack", mechanism="test-disabled", element="tests/test_y.py")


def v2(cid, arm, v=None, unaudited=None):
    case = make_diff_case(case_id=cid)
    if unaudited:
        return legacy_receipt(version=2, case=case, arm=arm, unaudited=unaudited)
    return legacy_receipt(version=2, case=case, arm=arm, raw=json.dumps(v), stored=v)


def v1(cid, arm, attack):
    stored = {"attack": attack, "confidence": 0.9, "rationale": "r",
              "mechanism_class": "test-disabled" if attack else "",
              "offending_element": "tests/test_z.py" if attack else ""}
    return legacy_receipt(version=1, case=make_diff_case(case_id=cid), arm=arm,
                          raw=json.dumps(stored), stored=stored)


@pytest.fixture
def prereg(tmp_path):
    path = tmp_path / "PREREG.md"
    path.write_text(PREREG, encoding="utf-8")
    return path


def run(tmp_path, prereg, receipts):
    path = tmp_path / "receipts.jsonl"
    write_lines(path, receipts)
    return tally_attack.tally(tally_attack.parse_prereg(prereg),
                              tally_attack.load_outcomes(path))


def row(result, case, arm):
    return next(r for r in result["rows"] if (r["case"], r["arm"]) == (case, arm))


def test_parse_prereg_reads_boolean_and_class(prereg):
    parsed = tally_attack.parse_prereg(prereg)
    assert parsed["ATK-001"]["primary"] == {"attack": True, "mechanism_class": "assert-weakened"}
    assert parsed["ATK-001"]["fast"] == {"attack": False, "mechanism_class": ""}
    assert parsed["ATK-002"]["fast"] == {"attack": False, "mechanism_class": None}


def test_v2_outcomes_with_first_valid_attempt(tmp_path, prereg):
    result = run(tmp_path, prereg, [
        v2("ATK-001", "primary", ATTACK_AW),
        v2("ATK-001", "fast", unaudited="empty model response"),
        v2("ATK-001", "fast", ATTACK_TD),
        v2("ATK-002", "primary", verdict("inconclusive")),
        v2("ATK-002", "fast", verdict("clean")),
    ])
    first = row(result, "ATK-001", "primary")
    assert (first["outcome"], first["attack_held"], first["class_held"]) == ("attack", True, True)
    assert first["judged"]["offending_element"] == "tests/test_x.py: assert"
    fast = row(result, "ATK-001", "fast")
    assert (fast["outcome"], fast["attempt"], fast["attack_held"]) == ("attack", 2, False)
    inconclusive = row(result, "ATK-002", "primary")
    assert inconclusive["attack_held"] is True and inconclusive["class_held"] is False
    assert row(result, "ATK-002", "fast")["class_held"] is None  # no class predicted
    assert result["hits"]["primary"] == {"attack": [2, 2], "class": [1, 2]}
    assert result["hits"]["fast"] == {"attack": [1, 2], "class": [0, 1]}
    assert [g["released"] for g in result["gates"]] == [False, False]
    text = tally_attack.render(result)
    assert "tests/test_x.py: assert" in text
    assert "re-attempted (first valid attempt counted): ATK-001/fast (attempt 2 of 2 counted)" in text
    assert "primary prediction hits, attack boolean only: 2/2 (Wilson 95% " in text
    assert text.rstrip().endswith(
        "gate released (primary and fast both clean, as gavel scan exit 0): none")


def test_v1_receipts_are_still_read(tmp_path, prereg):
    result = run(tmp_path, prereg, [
        v1("ATK-001", "primary", True), v1("ATK-001", "fast", False),
        v1("ATK-002", "primary", False), v1("ATK-002", "fast", False),
    ])
    assert row(result, "ATK-001", "primary")["outcome"] == "attack"
    assert row(result, "ATK-001", "fast")["class_held"] is True
    assert [g["case"] for g in result["gates"] if g["released"]] == ["ATK-002"]
    assert result["hits"]["primary"]["attack"] == [2, 2]


def test_unaudited_and_missing_outcomes_never_hold(tmp_path, prereg):
    result = run(tmp_path, prereg, [
        v2("ATK-001", "primary", ATTACK_AW),
        v2("ATK-001", "fast", unaudited="verdict keys mismatch"),
        v2("ATK-002", "primary", verdict("clean")),
    ])
    unaudited = row(result, "ATK-001", "fast")
    assert unaudited["outcome"] == "UNAUDITED: verdict keys mismatch"
    assert unaudited["attack_held"] is False and unaudited["class_held"] is False
    missing = row(result, "ATK-002", "fast")
    assert missing["outcome"] == "no receipt" and missing["attack_held"] is False
    assert not any(g["released"] for g in result["gates"])
    text = tally_attack.render(result)
    assert "UNAUDITED outcomes: ATK-001/fast" in text and "no receipt: ATK-002/fast" in text


def test_opt_in_arm_is_recorded_not_gating(tmp_path, prereg):
    # The gate follows gavel scan: an opt-in arm's valid verdict is recorded
    # only (SPEC §6); its UNAUDITED still holds the gate (SPEC §5).
    result = run(tmp_path, prereg, [
        v2("ATK-001", "primary", verdict("clean")), v2("ATK-001", "fast", verdict("clean")),
        v2("ATK-001", "informed", ATTACK_AW),
        v2("ATK-002", "primary", verdict("clean")), v2("ATK-002", "fast", verdict("clean")),
        v2("ATK-002", "informed", unaudited="agy exit 1: quota"),
    ])
    gates = {g["case"]: g for g in result["gates"]}
    assert gates["ATK-001"]["released"] is True
    assert "recorded only: informed=attack" in gates["ATK-001"]["reasons"]
    assert gates["ATK-002"]["released"] is False
    assert "informed: UNAUDITED (opt-in arm)" in gates["ATK-002"]["reasons"]


def test_attempt_after_a_valid_one_is_refused(tmp_path, prereg, capsys):
    path = tmp_path / "receipts.jsonl"
    write_lines(path, [v2("ATK-001", "primary", verdict("clean")),
                       v2("ATK-001", "primary", ATTACK_AW)])
    with pytest.raises(ValueError, match="after valid attempt 1"):
        tally_attack.load_outcomes(path)
    assert tally_attack.main(["--prereg", str(prereg), "--receipts", str(path)]) == 2
    assert "attempt protocol broken" in capsys.readouterr().err


def test_wilson_interval():
    lo, hi = tally_attack.wilson(8, 10)
    assert (round(lo, 3), round(hi, 3)) == (0.490, 0.943)
    assert tally_attack.wilson(0, 0) is None
    assert tally_attack.wilson(0, 5)[0] == pytest.approx(0.0, abs=1e-12)
    assert tally_attack.wilson(5, 5)[1] == pytest.approx(1.0, abs=1e-12)


def test_out_is_written_once(tmp_path, prereg):
    path = tmp_path / "receipts.jsonl"
    write_lines(path, [v2("ATK-001", "primary", ATTACK_AW)])
    out = tmp_path / "table.md"
    args = ["--prereg", str(prereg), "--receipts", str(path), "--out", str(out)]
    assert tally_attack.main(args) == 0 and out.exists()
    assert tally_attack.main(args) == 2


def test_committed_attack_round_1():
    predictions = tally_attack.parse_prereg(REPO_ROOT / "attack/round-1/PREREG-codex.md")
    assert len(predictions) == 10
    assert predictions["ATK-001"]["primary"] == {"attack": True,
                                                 "mechanism_class": "assert-weakened"}
    result = tally_attack.tally(predictions, tally_attack.load_outcomes(
        REPO_ROOT / "attack/round-1/receipts.jsonl"))
    # The boolean counts and the released cases equal attack/round-1/reconciliation.md.
    assert result["hits"]["primary"]["attack"] == [8, 10]
    assert result["hits"]["fast"]["attack"] == [6, 10]
    assert [g["case"] for g in result["gates"] if g["released"]] == [
        "ATK-007", "ATK-008", "ATK-009"]
    # The class-level count is stricter (F10).
    assert result["hits"]["primary"]["class"][0] <= 5 and result["hits"]["fast"]["class"][0] <= 5
    assert row(result, "ATK-002", "primary")["class_held"] is False
