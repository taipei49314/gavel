"""DRAFT, NOT FOR APPROVAL: judge-smoke helper (runs inside the judge-smoke job only).

Judges the synthetic smoke cases (smoke/SMOKE-*.json; PREREG procedure 1: never
exam material) with one local arm (--arm, primary by default), RUNS times
each, through gavel.qualify.judge_case, the single judgment path of exam and
scan (live pin, approved-models check, pinned Ollama version, strict parsing,
truncation guards). Every judgment is written as a v3 receipt; there are no
re-attempts, because the smoke run measures how often a judgment fails.

Writes under --out: receipts.jsonl, smoke.json (per-judgment seconds, token
counts, done_reason, memory placement from /api/ps, UNAUDITED reasons) and
the determinism and truncation findings.

prompt_eval_count stability: gavel's truncation guard (CR-16) trusts the
daemon's prompt_eval_count. If the daemon counts only the prompt tokens it
did not take from its KV cache, a repeated prompt reports fewer tokens and a
full context can go unseen. So the count of runs 2..n of a case is compared
with run 1, and any run whose count differs is flagged and fails the smoke.
Every prompt also shares the instruction header, so even run 1 of a later
case may be counted after a cached prefix; the headroom figure is only as
good as the counts, and the lock must settle how the pinned runtime counts.

--cold-first settles it on the host: before run 1 of each case the arm's
model is unloaded (keep_alive 0) and loaded again with the same options, so
run 1 starts from an empty prompt cache while runs 2..n repeat a prompt the
runner has just cached. A count that does not depend on the cache is the same
in every run; the reload's seconds are recorded apart from the judgment's.

--co-load MODEL loads another approved model first and leaves it loaded, so
the arm's model shares memory with it, as when two arms run one after the
other; /api/ps records where each model was placed (size_vram).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gavel.judge import DEFAULT_OPTIONS, strict_loads  # noqa: E402
from gavel.prompt import MECHANISM_CLASSES  # noqa: E402
from gavel.qualify import ARMS, judge_case  # noqa: E402
from gavel.receipts import ReceiptLog, build_receipt, verify_file  # noqa: E402


def ps(base_url: str):
    try:
        with urllib.request.urlopen(f"{base_url}/api/ps", timeout=10) as response:
            listed = json.loads(response.read().decode("utf-8"))
        return [{"name": m.get("name"), "size": m.get("size"), "size_vram": m.get("size_vram")}
                for m in listed.get("models", [])]
    except (OSError, ValueError):
        return None


def post(base_url: str, path: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(f"{base_url}{path}",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def reload_cold(base_url: str, model: str, timeout: float) -> float:
    """Unload model, wait until /api/ps no longer lists it, then load it again
    with the judgment options (another num_ctx would make the daemon reload it
    on the next call). Returns the seconds the load took."""
    post(base_url, "/api/generate", {"model": model, "keep_alive": 0}, timeout)
    deadline = time.monotonic() + 120
    while True:
        listed = ps(base_url)
        if listed is None:
            raise RuntimeError("/api/ps unavailable while waiting for the unload")
        if not any(m["name"] == model for m in listed):
            break
        if time.monotonic() > deadline:
            raise RuntimeError(f"{model} still loaded 120 s after the unload request")
        time.sleep(1)
    started = time.monotonic()
    post(base_url, "/api/generate", {"model": model, "options": DEFAULT_OPTIONS}, timeout)
    return round(time.monotonic() - started, 3)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ollama-version", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--arm", default="primary",
                        choices=[name for name, spec in ARMS.items()
                                 if spec["transport"] == "ollama"])
    parser.add_argument("--cold-first", action="store_true")
    parser.add_argument("--co-load", choices=sorted({spec["model"] for spec in ARMS.values()
                                                     if spec["transport"] == "ollama"}))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    model = ARMS[args.arm]["model"]
    log = ReceiptLog(out / "receipts.jsonl")
    if args.co_load:
        post(args.base_url, "/api/generate", {"model": args.co_load, "options": DEFAULT_OPTIONS},
             args.timeout)
    judgments = []
    for path in sorted((ROOT / "smoke").glob("SMOKE-*.json")):
        case = strict_loads(path.read_bytes().decode("utf-8"))
        for run in range(1, args.runs + 1):
            cold = args.cold_first and run == 1
            load_seconds = reload_cold(args.base_url, model, args.timeout) if cold else None
            started = time.monotonic()
            result = judge_case(case, model, args.base_url, args.timeout,
                                pinned_runtime={"ollama_version": args.ollama_version})
            seconds = round(time.monotonic() - started, 3)
            receipt = log.append(build_receipt(case_id=case["case_id"], arm=args.arm, run=run,
                                               attempt=1, judgment=result))
            generation = result.get("generation") or {}
            judgments.append({
                "case_id": case["case_id"], "run": run, "seconds": seconds,
                "cold": cold, "load_seconds": load_seconds,
                "receipt_id": receipt["receipt_id"], "unaudited": result["unaudited"],
                "verdict": result["verdict"], "raw_sha256": (
                    None if result["raw"] is None else
                    hashlib.sha256(result["raw"].encode("utf-8")).hexdigest()),
                "prompt_eval_count": generation.get("prompt_eval_count"),
                "eval_count": generation.get("eval_count"),
                "done_reason": generation.get("done_reason"),
                "num_ctx": (result.get("options") or {}).get("num_ctx"),
                "loaded": ps(args.base_url)})
    verify_file(out / "receipts.jsonl", MECHANISM_CLASSES, content=True,
                expect_head=log.head, expect_count=log.count)
    cases = sorted({j["case_id"] for j in judgments})
    determinism = {}
    for cid in cases:
        runs = [j for j in judgments if j["case_id"] == cid]
        determinism[cid] = {
            "verdicts_identical": len({json.dumps(j["verdict"], sort_keys=True) for j in runs}) == 1,
            "raw_identical": len({j["raw_sha256"] for j in runs}) == 1}
    prompt_counts = {}
    for cid in cases:
        runs = sorted((j for j in judgments if j["case_id"] == cid), key=lambda j: j["run"])
        first = runs[0]["prompt_eval_count"]
        prompt_counts[cid] = {
            "per_run": {str(j["run"]): j["prompt_eval_count"] for j in runs},
            "runs_differing_from_run_1": [j["run"] for j in runs[1:]
                                          if j["prompt_eval_count"] != first]}
    counts_differ = {cid: c["runs_differing_from_run_1"] for cid, c in prompt_counts.items()
                     if c["runs_differing_from_run_1"]}
    valid = [j for j in judgments if not j["unaudited"]]
    headroom = [j["num_ctx"] - j["prompt_eval_count"] for j in judgments
                if isinstance(j["num_ctx"], int) and isinstance(j["prompt_eval_count"], int)]
    summary = {
        "arm": args.arm, "cold_first": args.cold_first, "co_load": args.co_load,
        "model": model, "options": DEFAULT_OPTIONS, "judgments": len(judgments),
        "valid": len(valid), "unaudited": [j for j in judgments if j["unaudited"]],
        "seconds": {"min": min(j["seconds"] for j in judgments),
                    "median": statistics.median(j["seconds"] for j in judgments),
                    "max": max(j["seconds"] for j in judgments)},
        "determinism": determinism,
        "truncation": {"done_reason_length": [j for j in judgments if j["done_reason"] == "length"],
                       "min_context_headroom_tokens": min(headroom) if headroom else None,
                       "prompt_eval_count": prompt_counts,
                       "prompt_eval_count_differs": counts_differ},
        "receipts": {"count": log.count, "head": log.head},
        "per_judgment": judgments}
    (out / "smoke.json").write_text(json.dumps(summary, sort_keys=True, indent=2,
                                               ensure_ascii=False) + "\n",
                                    encoding="utf-8", newline="\n")
    ok = (len(valid) == len(judgments)
          and all(d["verdicts_identical"] for d in determinism.values())
          and not summary["truncation"]["done_reason_length"]
          and not counts_differ)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
