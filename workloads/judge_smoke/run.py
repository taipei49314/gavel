"""DRAFT, NOT FOR APPROVAL: judge-smoke.

On the one EC pool host Nelson names, after judge-host-prepare: start the
pinned Ollama from the cache on a private loopback port and judge the three
synthetic smoke cases (smoke/SMOKE-*.json, never exam material) with the
primary arm only, three times each (smoke.py). It measures what the round-3
lock needs to know about the host: seconds per judgment, determinism over
three runs at temperature 0, context headroom and truncation, whether
prompt_eval_count stays the same over repeated runs (a cached prompt
counted short would blind the truncation guard), how often a judgment is
UNAUDITED, and where the model was loaded (/api/ps size_vram).

No exam case, no re-attempt, no informed arm. Refuses unless NAMED_HOST and
the Ollama pins in workloads/judge_common.py are filled in, and never runs on a
work machine. Uses the pool Python directly: gavel has no runtime dependency.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import judge_common as jc  # noqa: E402

WORKLOAD = "judge-smoke"
RUNS = 3
JUDGMENT_TIMEOUT_S = 1800  # DRAFT: generous for CPU inference; the lock fixes the exam's value


def main() -> int:
    try:
        paths = jc.gate(WORKLOAD)
    except jc.Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    out, problems, record = paths["out"], [], {"workload": WORKLOAD, "host": paths["host"]}
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    record["hardware"] = jc.hardware(paths["cache"])
    record["models"] = {m: jc.verify_local_model(paths["models"], m, blobs=False)
                        for m in jc.MODELS}
    code = None
    try:
        if not all(v["ok"] for v in record["models"].values()):
            raise RuntimeError("approved models are not prepared; run judge-host-prepare")
        with jc.OllamaServer(paths, out / "ollama-serve.log") as server:
            record["ollama_version"] = server.version
            record["tags"] = server.tags()
            env = {k: v for k, v in os.environ.items() if not k.startswith("GAVEL_")}
            env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
                       GAVEL_AGY=str(paths["work"] / "no-agy" / "agy.exe"))
            done = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", str(Path(__file__).with_name("smoke.py")),
                 "--base-url", server.base_url, "--ollama-version", server.version,
                 "--out", str(out / "smoke"), "--runs", str(RUNS),
                 "--timeout", str(JUDGMENT_TIMEOUT_S)],
                cwd=jc.ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                timeout=RUNS * 3 * JUDGMENT_TIMEOUT_S + 600)
            code = done.returncode
            (out / "smoke.stdout").write_bytes(done.stdout)
            (out / "smoke.stderr").write_bytes(done.stderr)
        if code != 0:
            problems.append(f"smoke.py exit {code}: an UNAUDITED judgment, a nondeterministic "
                            f"verdict, a truncated output or a prompt_eval_count that differs "
                            f"between runs of a case (see smoke/smoke.json)")
    except Exception as exc:  # recorded, then the job fails
        problems.append(f"{type(exc).__name__}: {exc}")
    record["seconds"] = round(time.monotonic() - started, 1)
    record["problems"] = problems
    jc.write_json(out / "judge-smoke.json", record)
    smoke = {}
    try:
        smoke = json.loads((out / "smoke" / "smoke.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    seconds = smoke.get("seconds", {})
    lines = ["# judge-smoke (DRAFT workload)", "",
             f"Result: {'PASS' if not problems else 'FAIL'} on {paths['host']}", "",
             f"- Ollama {record.get('ollama_version')}; primary {smoke.get('model')}; "
             f"{smoke.get('valid')}/{smoke.get('judgments')} judgments valid",
             f"- Seconds per judgment: min {seconds.get('min')}, median {seconds.get('median')}, "
             f"max {seconds.get('max')}",
             f"- Determinism over {RUNS} runs: {json.dumps(smoke.get('determinism'), sort_keys=True)}",
             f"- Truncation: {json.dumps(smoke.get('truncation', {}).get('min_context_headroom_tokens'))} "
             f"tokens minimum context headroom; length stops: "
             f"{len(smoke.get('truncation', {}).get('done_reason_length', []))}",
             f"- prompt_eval_count differing from run 1 (KV-cache reuse would hide tokens "
             f"from the truncation guard): "
             f"{json.dumps(smoke.get('truncation', {}).get('prompt_eval_count_differs'), sort_keys=True)}",
             "- Smoke cases only; no exam case was judged.", ""]
    lines += [f"- problem: {p}" for p in problems]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
