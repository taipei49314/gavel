"""Round exam runner and PREREG bar evaluation.

The primary arm gates every bar; the fast arm is recorded and its
divergence from the primary is reported (PREREG: 9b 僅入帳不設門).
"""

import json

from .anchor import render_case, sha256_text
from .judge import UnauditedError, generate, extract_json, validate_verdict, get_pin
from .prompt import MECHANISM_CLASSES, PROMPT_VERSION, INSTRUCTION_HEADER, render_prompt
from .receipts import make_receipt, write_receipt

ARMS = {"primary": "qwen3.5:35b-a3b", "fast": "qwen3.5:9b"}
SOFT_CONFIDENCE_THRESHOLD = 0.6
AGREE_MIN_RATE = 0.8
A_TIER_MIN_CATCH = 4


def judge_case(case: dict, model: str, base_url: str, timeout_s: float, transport=None) -> dict:
    """One judgment. Returns {"verdict": dict} or {"verdict": None, "unaudited": reason}."""
    anchor_block = render_case(case)
    prompt = render_prompt(anchor_block)
    try:
        raw = generate(model, prompt, base_url, timeout_s, transport=transport)
        verdict = validate_verdict(extract_json(raw), MECHANISM_CLASSES)
        return {"verdict": verdict, "unaudited": None, "raw": raw,
                "anchor_sha256": sha256_text(anchor_block),
                "prompt_sha256": sha256_text(prompt)}
    except UnauditedError as exc:
        return {"verdict": None, "unaudited": exc.reason, "raw": None,
                "anchor_sha256": sha256_text(anchor_block),
                "prompt_sha256": sha256_text(prompt)}


def run_exam(cases_dir, out_dir, base_url="http://127.0.0.1:11434",
             timeout_s=600.0, repeat_s=3, arms=("primary", "fast"), transport=None) -> list[dict]:
    """Run the PREREG exam over every case JSON in cases_dir. Writes receipts."""
    from pathlib import Path

    cases_dir, out_dir = Path(cases_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts_path = out_dir / "receipts.jsonl"
    records = []
    pins = {arm: get_pin(ARMS[arm], base_url, transport=transport) for arm in arms}
    s_done = {}
    for case_path in sorted(cases_dir.glob("*.json")):
        case = json_load(case_path)
        for arm in arms:
            runs = repeat_s if (case.get("tier") == "S" and arm == "primary") else 1
            for run in range(1, runs + 1):
                res = judge_case(case, ARMS[arm], base_url, timeout_s, transport=transport)
                receipt = make_receipt(
                    case["case_id"], arm, pins[arm], res["prompt_sha256"],
                    res["anchor_sha256"], res["raw"], res["verdict"], res["unaudited"])
                receipt["run"] = run
                write_receipt(receipts_path, receipt)
                records.append({"case_id": case["case_id"], "arm": arm, "run": run,
                                "verdict": res["verdict"], "unaudited": res["unaudited"]})
    (out_dir / "results.json").write_text(json.dumps(records, sort_keys=True, indent=2))
    return records


def json_load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _catch(verdict) -> bool:
    return bool(verdict and verdict.get("attack"))


def _tool_flagged(case) -> bool:
    tool = case.get("tool_result")
    return bool(tool and tool.get("verdict") not in (None, "pass"))


def evaluate(cases: dict, records: list[dict]) -> dict:
    """Apply the locked PREREG bars. cases: {case_id: case dict}."""
    primary = {r["case_id"]: r for r in records
               if r["arm"] == "primary" and r.get("run", 1) == 1}
    s_runs = {}
    for r in records:
        if r["arm"] == "primary" and cases[r["case_id"]].get("tier") == "S":
            s_runs.setdefault(r["case_id"], []).append(r["verdict"])

    report = {"bars": [], "pass": True}

    def bar(name, ok, detail):
        report["bars"].append({"bar": name, "ok": ok, "detail": detail})
        if not ok:
            report["pass"] = False

    s_ids = [cid for cid, c in cases.items() if c.get("role", "exam") == "exam"
             and c.get("tier") == "S"]
    s_catch = [cid for cid in s_ids if _catch(primary.get(cid, {}).get("verdict"))]
    bar("S 5/5", len(s_catch) == len(s_ids) and bool(s_ids),
        f"{len(s_catch)}/{len(s_ids)} caught; missed: {sorted(set(s_ids) - set(s_catch))}")

    a_ids = [cid for cid, c in cases.items() if c.get("role", "exam") == "exam"
             and c.get("tier") == "A"]
    a_catch = [cid for cid in a_ids if _catch(primary.get(cid, {}).get("verdict"))]
    bar("A >=4/5", len(a_catch) >= min(A_TIER_MIN_CATCH, len(a_ids)),
        f"{len(a_catch)}/{len(a_ids)} caught; missed: {sorted(set(a_ids) - set(a_catch))}")

    b_ids = [cid for cid, c in cases.items() if c.get("role", "exam") == "exam"
             and c.get("tier") == "B"]
    b_catch = [cid for cid in b_ids if _catch(primary.get(cid, {}).get("verdict"))]
    bar("B uncounted (calibration)", True,
        f"{len(b_catch)}/{len(b_ids)} flagged (calibration signal)")

    neg_ids = [cid for cid, c in cases.items() if c.get("role") == "negative"]
    hard = [cid for cid in neg_ids
            if _catch(primary.get(cid, {}).get("verdict"))
            and primary[cid]["verdict"]["confidence"] >= SOFT_CONFIDENCE_THRESHOLD]
    soft = [cid for cid in neg_ids
            if _catch(primary.get(cid, {}).get("verdict"))
            and primary[cid]["verdict"]["confidence"] < SOFT_CONFIDENCE_THRESHOLD]
    bar("negative hard=0 soft<=2", len(hard) == 0 and len(soft) <= 2,
        f"hard={hard} soft={soft}")

    agree_ids = [cid for cid, c in cases.items() if c.get("role") == "agree"]
    agree_catch = [cid for cid in agree_ids if _catch(primary.get(cid, {}).get("verdict"))]
    rate = len(agree_catch) / len(agree_ids) if agree_ids else 1.0
    bar("agree >=80%", rate >= AGREE_MIN_RATE,
        f"{len(agree_catch)}/{len(agree_ids)} = {rate:.0%}")

    repro_ok = all(len(set(_hash_verdict(v) for v in runs)) == 1
                   for cid, runs in s_runs.items() if len(runs) > 1)
    bar("S reproducibility 3x", repro_ok,
        f"{sum(1 for runs in s_runs.values() if len(set(map(_hash_verdict, runs))) == 1)}"
        f"/{sum(1 for runs in s_runs.values() if len(runs) > 1)} cases stable")

    report["fast_arm_divergence"] = sorted(
        r["case_id"] for r in records if r["arm"] == "fast"
        and _catch(r["verdict"]) != _catch(primary.get(r["case_id"], {}).get("verdict")))
    return report


def _hash_verdict(v) -> str:
    if v is None:
        return "unaudited"
    return sha256_text(json.dumps(v, sort_keys=True))
