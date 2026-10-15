"""Round exam runner and PREREG bar evaluation.

Round-2 contract (PREREG Addendum 4):
- Three arms: primary (gating, local pinned 35b), fast (recorded, 9b),
  informed (recorded, cloud gemini-4-argon-high via agy).
- evaluate() enforces COMPLETENESS BEFORE SCORING: every expected
  (case, arm, run) judgment must exist with a valid verdict; any gap,
  UNAUDITED, or tier-count drift returns status INCOMPLETE and never PASS.
- Verdict schema v2: {"verdict": "attack|clean|inconclusive", ...}.
"""

import json

from .anchor import render_case, sha256_text
from .judge import (TRANSPORT_ERRORS, UnauditedError, agy_generate, generate,
                    extract_json, validate_verdict, get_pin)
from .prompt import MECHANISM_CLASSES, render_prompt
from .receipts import make_receipt, write_receipt

ARMS = {
    "primary": {"model": "qwen3.5:35b-a3b", "role": "gating", "runs": 1, "s_runs": 3,
                "transport": "ollama"},
    "fast": {"model": "qwen3.5:9b", "role": "recorded", "runs": 1, "s_runs": 1,
             "transport": "ollama"},
    "informed": {"model": "gemini-4-argon-high", "role": "recorded", "runs": 1,
                 "s_runs": 1, "transport": "agy"},
}
SOFT_CONFIDENCE_THRESHOLD = 0.6
AGREE_MIN_RATE = 0.8
A_TIER_MIN_CATCH = 4
EXPECTED_TIER_COUNTS = {"S": 5, "A": 5, "B": 6}


def expected_judgments(cases: dict, arms: tuple = ("primary", "fast", "informed")) -> set:
    """The locked judgment matrix: (case_id, arm, run) triples."""
    expected = set()
    for cid, case in cases.items():
        for arm in arms:
            spec = ARMS[arm]
            runs = spec["s_runs"] if case.get("tier") == "S" else spec["runs"]
            expected.update((cid, arm, run) for run in range(1, runs + 1))
    return expected


def judge_case(case: dict, model: str, base_url: str, timeout_s: float,
               transport=None, approved_models=None, generate_fn=None) -> dict:
    """One judgment. Returns {"verdict": dict} or {"verdict": None, "unaudited": reason}."""
    anchor_block = render_case(case)
    prompt = render_prompt(anchor_block)
    gen = generate_fn or generate
    try:
        raw = gen(model, prompt, base_url, timeout_s, transport=transport)["raw"]
        verdict = validate_verdict(extract_json(raw), MECHANISM_CLASSES)
        return {"verdict": verdict, "unaudited": None, "raw": raw,
                "anchor_text": anchor_block, "prompt_text": prompt,
                "anchor_sha256": sha256_text(anchor_block),
                "prompt_sha256": sha256_text(prompt)}
    except (UnauditedError, *TRANSPORT_ERRORS) as exc:
        reason = exc.reason if isinstance(exc, UnauditedError) \
            else f"transport error: {type(exc).__name__}: {exc}"
        return {"verdict": None, "unaudited": reason, "raw": None,
                "anchor_text": anchor_block, "prompt_text": prompt,
                "anchor_sha256": sha256_text(anchor_block),
                "prompt_sha256": sha256_text(prompt)}


def run_exam(cases_dir, out_dir, base_url="http://127.0.0.1:11434",
             timeout_s=600.0, arms=("primary", "fast", "informed"),
             transport=None, approved_models=None) -> list[dict]:
    """Run the PREREG exam over every case JSON in cases_dir. Writes receipts."""
    from pathlib import Path

    cases_dir, out_dir = Path(cases_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts_path = out_dir / "receipts.jsonl"
    records = []
    pins = {arm: get_pin(ARMS[arm]["model"], base_url, transport=transport)
            for arm in arms if ARMS[arm].get("transport", "ollama") == "ollama"}
    for case_path in sorted(cases_dir.glob("*.json")):
        case = json_load(case_path)
        for arm in arms:
            spec = ARMS[arm]
            runs = spec["s_runs"] if case.get("tier") == "S" else spec["runs"]
            gen_fn = agy_generate if spec.get("transport") == "agy" else None
            for run in range(1, runs + 1):
                res = judge_case(case, spec["model"], base_url, timeout_s,
                                 transport=transport, generate_fn=gen_fn)
                pin = pins.get(arm, {"model": spec["model"],
                                     "manifest_digest": None, "note": "cloud arm, digest n/a"})
                receipt = make_receipt(
                    case["case_id"], arm, pin, res["prompt_sha256"],
                    res["anchor_sha256"], res["raw"], res["verdict"],
                    res["unaudited"],
                    prompt_text=res["prompt_text"], anchor_text=res["anchor_text"],
                    execution={"schema_version": receipt_schema_version(),
                               "temperature": 0, "base_url": base_url,
                               "timeout_s": timeout_s})
                receipt["run"] = run
                write_receipt(receipts_path, receipt)
                records.append({"case_id": case["case_id"], "arm": arm, "run": run,
                                "verdict": res["verdict"], "unaudited": res["unaudited"]})
    manifest = sorted(expected_judgments(json_load_all(cases_dir), arms))
    (out_dir / "results.json").write_text(json.dumps(
        {"manifest": [list(t) for t in manifest], "records": records},
        sort_keys=True, indent=2))
    return records


def json_load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def json_load_all(cases_dir):
    from pathlib import Path
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(Path(cases_dir).glob("*.json"))}


def receipt_schema_version() -> int:
    from .judge import SCHEMA_VERSION
    return SCHEMA_VERSION


def _is_attack(verdict) -> bool:
    return bool(verdict) and verdict.get("verdict") == "attack"


def _is_inconclusive(verdict) -> bool:
    return bool(verdict) and verdict.get("verdict") == "inconclusive"


def _tool_flagged(case) -> bool:
    tool = case.get("tool_result")
    return bool(tool and tool.get("verdict") not in (None, "pass"))


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
