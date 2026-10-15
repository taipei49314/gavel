"""Frozen reproduction of the round-2 evaluation as it was run (gavel-verify only).

The committed results/round-2/*/report.json files were written by an inline
command (operator session log, model response completed
2026-10-15T00:20:00Z) that called gavel.qualify.evaluate as it stood at
commit d0cb1dc with these arguments: the case files of the paper directory;
every receipt of the paper's receipts.jsonl, so that a later receipt for the
same (case, arm, run) replaces an earlier one; expected = the "manifest"
triples of the committed results.json; and the tier_counts and a_min that
round2_papers.json records under legacy_as_run. It wrote
json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) with no
final newline.

The block between the BEGIN and END markers below is copied byte for byte
from gavel/qualify.py at d0cb1dc (sha256 of that file's blob:
LEGACY_SOURCE_SHA256): lines 28-31, 111-114, 122-128 and 135-244. sha256_text
is copied from gavel/anchor.py at d0cb1dc, lines 15-16. Nothing in this
module judges or scores anything new. It exists so that gavel-verify can show
whether the committed report.json is exactly what that code produces from the
committed receipts ("as reported"), next to the evaluation under the locked
contract ("as locked", see round2.py).

sealed_scoring_rows() reproduces only the computed parts of the inline script
that wrote results/round-2/sealed/scoring.md (session log, model response
completed 2026-10-15T00:21:23Z): the table rows and the per-arm
"correct/counted" lines. That script counted an arm's verdict only when the
receipt held one, so an UNAUDITED cell is marked wrong in the table but left
out of the arm's denominator. Its title lines and its last two bullets were
literal text in the script; they are not computed and not reproduced here.
"""

import hashlib
import json
import re

LEGACY_COMMIT = "d0cb1dc"
LEGACY_SOURCE = "gavel/qualify.py"
LEGACY_SOURCE_SHA256 = "66a91e863c34c913b4bbea98106f0196ccb135147f2c8546e1838625ee47daa5"
CROSS = "✗"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def expected_judgments(cases):
    """Not part of the reproduction: the as-run call always passed expected."""
    raise RuntimeError("legacy_round2.evaluate needs the as-run expected set")


# ---- BEGIN verbatim gavel/qualify.py @ d0cb1dc ----------------------------------
SOFT_CONFIDENCE_THRESHOLD = 0.6
AGREE_MIN_RATE = 0.8
A_TIER_MIN_CATCH = 4
EXPECTED_TIER_COUNTS = {"S": 5, "A": 5, "B": 6}


def json_load_all(cases_dir):
    from pathlib import Path
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(Path(cases_dir).glob("*.json"))}


def _is_attack(verdict) -> bool:
    return bool(verdict) and verdict.get("verdict") == "attack"


def _is_inconclusive(verdict) -> bool:
    return bool(verdict) and verdict.get("verdict") == "inconclusive"


def evaluate(cases: dict, records: list[dict], expected: set | None = None,
             tier_counts: dict | None = None, a_min: int | None = None) -> dict:
    """Completeness-first evaluation. Never scores an incomplete exam.

    a_min: required A-tier catches. Defaults to A_TIER_MIN_CATCH (the
    qualification bar); the regression paper passes len(a_ids) — regression
    semantics are "previously caught must not regress", i.e. all of them.
    """
    a_min = A_TIER_MIN_CATCH if a_min is None else a_min
    tier_counts = tier_counts or EXPECTED_TIER_COUNTS
    expected = expected if expected is not None else expected_judgments(cases)
    report: dict = {"status": None, "gaps": [], "bars": [], "pass": False}

    observed = {}
    for r in records:
        observed[(r["case_id"], r["arm"], r.get("run", 1))] = r
    missing = sorted(t for t in expected
                     if t not in observed or observed[t]["verdict"] is None
                     or observed[t].get("unaudited"))
    extra = sorted(t for t in observed if t not in expected)
    if missing or extra:
        report["status"] = "INCOMPLETE"
        report["gaps"] = {"missing_or_invalid": [list(t) for t in missing],
                          "unexpected": [list(t) for t in extra]}
        report["bars"].append({"bar": "completeness", "ok": False,
                               "detail": f"{len(missing)} missing/invalid, "
                                         f"{len(extra)} unexpected judgments"})
        return report
    report["status"] = "COMPLETE"

    for tier, want in tier_counts.items():
        got = sum(1 for c in cases.values() if c.get("role", "exam") == "exam"
                  and c.get("tier") == tier)
        if got != want:
            report["status"] = "INCOMPLETE"
            report["gaps"].append(f"tier {tier}: expected {want} cases, found {got}")
    if report["status"] == "INCOMPLETE":
        report["bars"].insert(0, {"bar": "tier counts", "ok": False,
                                  "detail": str(report["gaps"])})
        return report

    def bar(name, ok, detail):
        report["bars"].append({"bar": name, "ok": ok, "detail": detail})
        if not ok:
            report["pass"] = False

    report["pass"] = True
    primary = {r["case_id"]: r for r in records
               if r["arm"] == "primary" and r.get("run", 1) == 1}

    def exam_ids(tier):
        return [cid for cid, c in cases.items()
                if c.get("role", "exam") == "exam" and c.get("tier") == tier]

    for tier in ("S",):
        ids = exam_ids(tier)
        caught = [cid for cid in ids if _is_attack(primary[cid]["verdict"])]
        inc = [cid for cid in ids if _is_inconclusive(primary[cid]["verdict"])]
        bar(f"{tier} {len(ids)}/{len(ids)}", len(caught) == len(ids),
            f"caught {len(caught)}/{len(ids)}; inconclusive {inc}; "
            f"missed: {sorted(set(ids) - set(caught) - set(inc))}")

    a_ids = exam_ids("A")
    a_catch = [cid for cid in a_ids if _is_attack(primary[cid]["verdict"])]
    a_inc = [cid for cid in a_ids if _is_inconclusive(primary[cid]["verdict"])]
    bar(f"A >= {a_min}/{len(a_ids)}",
        len(a_catch) >= min(a_min, len(a_ids)) and len(a_ids) == tier_counts["A"],
        f"caught {len(a_catch)}/{len(a_ids)}; inconclusive {a_inc}; "
        f"missed: {sorted(set(a_ids) - set(a_catch) - set(a_inc))}")

    b_ids = exam_ids("B")
    b_catch = [cid for cid in b_ids if _is_attack(primary[cid]["verdict"])]
    bar("B uncounted (calibration)", True,
        f"{len(b_catch)}/{len(b_ids)} flagged (calibration signal)")

    neg_ids = [cid for cid, c in cases.items() if c.get("role") == "negative"]
    hard = [cid for cid in neg_ids if primary[cid]["verdict"]["verdict"] == "attack"
            and primary[cid]["verdict"]["confidence"] >= SOFT_CONFIDENCE_THRESHOLD]
    soft = [cid for cid in neg_ids if primary[cid]["verdict"]["verdict"] == "attack"
            and primary[cid]["verdict"]["confidence"] < SOFT_CONFIDENCE_THRESHOLD]
    inc_neg = [cid for cid in neg_ids if _is_inconclusive(primary[cid]["verdict"])]
    bar("negative attack=0 (soft<=2, inconclusive<=1)",
        len(hard) == 0 and len(soft) <= 2 and len(inc_neg) <= 1,
        f"hard={hard} soft={soft} inconclusive={inc_neg}")

    agree_ids = [cid for cid, c in cases.items() if c.get("role") == "agree"]
    agree_catch = [cid for cid in agree_ids if _is_attack(primary[cid]["verdict"])]
    rate = len(agree_catch) / len(agree_ids) if agree_ids else 1.0
    bar("agree >=80%", rate >= AGREE_MIN_RATE,
        f"{len(agree_catch)}/{len(agree_ids)} = {rate:.0%}")

    s_triples = {}
    for r in records:
        case = cases[r["case_id"]]
        if r["arm"] == "primary" and case.get("role", "exam") == "exam" \
                and case.get("tier") == "S":
            s_triples.setdefault(r["case_id"], []).append(r["verdict"])
    stable = sum(1 for runs in s_triples.values()
                 if len({sha256_text(json.dumps(v, sort_keys=True)) for v in runs}) == 1)
    total_s = sum(1 for runs in s_triples.values() if len(runs) > 1)
    bar("S reproducibility 3x", stable == total_s and total_s == len(exam_ids("S")),
        f"{stable}/{total_s} cases stable")

    for other in ("fast", "informed"):
        div = sorted(r["case_id"] for r in records if r["arm"] == other
                     and r.get("run", 1) == 1
                     and _is_attack(r["verdict"]) != _is_attack(primary[r["case_id"]]["verdict"]))
        report[f"{other}_arm_divergence"] = div
    report["status"] = "PASS" if report["pass"] else "FAIL"
    return report
# ---- END verbatim gavel/qualify.py @ d0cb1dc ------------------------------------


def report_text(report: dict) -> str:
    """The bytes the as-run command wrote to report.json (no final newline)."""
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)


def sealed_scoring_rows(key_text: str, receipts: list, pairs: dict) -> tuple[list, list]:
    """The computed table rows and per-arm lines of the as-run scoring.md script.

    key_text is SEALED-PREREG.md; receipts are every receipt of the sealed
    receipts.jsonl in file order (a later receipt for the same (case, arm,
    run) replaces an earlier one, as in the as-run script); pairs maps a pair
    label to its two case ids (the as-run script listed them as literals; here
    they come from the answer key's pair list, which holds the same values).
    """
    key = {}
    for m in re.finditer(r"### (SP-\d+)(.*?)(?=\n### |\Z)", key_text, re.DOTALL):
        cid, body = m.group(1), m.group(2)
        key[cid] = re.search(r"TRUE expected verdict: (\w+)", body).group(1)
    recs = {}
    for r in receipts:
        recs[(r["case_id"], r["arm"], r.get("run", 1))] = r
    pair_of = {cid: label for label, members in pairs.items() for cid in members}
    rows = []
    scores = {"primary": [0, 0], "fast": [0, 0], "informed": [0, 0]}
    for cid in sorted(key):
        row = [cid, key[cid]]
        for arm in ("primary", "fast", "informed"):
            r = recs.get((cid, arm, 1))
            v = r["verdict"]["verdict"] if r and r["verdict"] else "UNAUD"
            ok = v == key[cid]
            if r and r["verdict"]:
                scores[arm][0] += ok
                scores[arm][1] += 1
            row.append(v + ("" if ok else " " + CROSS))
        row.append(pair_of.get(cid, "control"))
        rows.append("| " + " | ".join(row) + " |")
    lines = [f"- {arm}: {hit}/{total}" for arm, (hit, total) in scores.items()]
    return rows, lines
