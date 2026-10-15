"""DRAFT, NOT FOR APPROVAL: gavel-exam.

Runs one locked round-3 paper once, on the one EC pool host Nelson names, with
`gavel exam --manifest <paper> --out out/<paper>` (gavel.qualify.run_paper):
preflight of every arm (live pin, approved models, pinned Ollama version)
before any judgment, harness-only immediate re-attempts of UNAUDITED slots up
to the manifest's attempt cap, every attempt receipted in a hash-chained v3
receipts file, and the report evaluated from the locked manifest alone. Then
`gavel verify --content --results` checks the receipts against the head and
count that results.json records.

Round-3 rules this draft enforces (docs/proposals/round-3-PREREG-DRAFT.md):
- the paper parameter selects one of the locked manifests in PAPERS (all
  "<TO-LOCK>" in this draft, which refuses);
- every arm of the manifest uses the local transport "ollama": the informed
  (agy) arm is excluded, because it is not sandboxed;
- the manifest pins the Ollama version this job runs, and fixes the options;
- the committed approved-models.json gated the exam: results.json and every
  receipt that passed the approval check record its sha256;
- one dispatch per paper: a paper whose exam wrote any receipt is never run
  again (the EC ledger row and the private receipt ref are the record;
  run_paper only refuses an output directory that already holds a run).

The job succeeds only when the paper is PASS (scored by bars) or COMPLETE
(external scoring, e.g. a sealed paper scored after reveal) and the receipts
verify. FAIL, INCOMPLETE, INVALID_* and refusals end as failure; the status is
in SUMMARY.md either way. Refuses unless NAMED_HOST, the Ollama pins and
PAPERS are filled in, and never runs on a work machine.
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

WORKLOAD = "gavel-exam"
# DRAFT: the locked manifests, as repository paths, fixed at the round-3 lock.
PAPERS = {
    "regression": "<TO-LOCK>",
    "known-sealed": "<TO-LOCK>",
    "sealed": "<TO-LOCK>",
}
JUDGMENT_TIMEOUT_S = None  # DRAFT: fixed at the lock from judge-smoke timings
EXAM_EXIT = {0: "PASS", 1: "FAIL", 2: "INVALID_PAPER, INVALID_RECORDS, INCOMPLETE or refused",
             3: "COMPLETE"}


def check_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_bytes().decode("utf-8"))
    arms = manifest.get("arms") or {}
    not_local = sorted(name for name, spec in arms.items() if spec.get("transport") != "ollama")
    if not_local:
        raise jc.Refused(f"arms {not_local} are not local; the informed arm is excluded in round-3")
    if (manifest.get("runtime") or {}).get("ollama_version") != jc.OLLAMA_VERSION:
        raise jc.Refused("the manifest does not pin the Ollama version this job runs")
    if not manifest.get("options"):
        raise jc.Refused("the manifest does not fix the generation options")
    return manifest


def approved_models_problems(exam_dir: Path, committed_sha256: str) -> list[str]:
    """The committed approved-models.json must be the file that gated the
    exam: results.json and every receipt that passed the check name it by
    sha256 (receipts without a record are judgments the check refused)."""
    problems = []
    try:
        results = json.loads((exam_dir / "results.json").read_text(encoding="utf-8"))
        recorded = (results.get("approved_models") or {}).get("sha256")
        if recorded != committed_sha256:
            problems.append(f"results.json records approved-models sha256 {recorded}, not the "
                            f"committed {committed_sha256}")
        with open(exam_dir / "receipts.jsonl", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                approved = json.loads(line).get("approved_models")
                if approved is not None and approved.get("sha256") != committed_sha256:
                    problems.append(f"receipts.jsonl:{lineno} was approved by another "
                                    f"approved-models file ({approved.get('sha256')})")
    except (OSError, ValueError, AttributeError) as exc:
        problems.append(f"approved-models record unreadable: {type(exc).__name__}: {exc}")
    return problems


def main() -> int:
    try:
        paths = jc.gate(WORKLOAD)
        parameters = json.loads(Path(os.environ["EC_WORKLOAD_PARAMETERS"]).read_text(encoding="utf-8"))
        paper = parameters.get("paper")
        manifest_rel = PAPERS.get(paper)
        if manifest_rel is None or manifest_rel == "<TO-LOCK>" or JUDGMENT_TIMEOUT_S is None:
            raise jc.Refused("DRAFT: the round-3 papers are not locked")
        manifest = check_manifest(jc.ROOT / manifest_rel)
    except (jc.Refused, OSError, ValueError, KeyError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    out, problems, record = paths["out"], [], {"workload": WORKLOAD, "host": paths["host"],
                                               "paper": paper, "manifest": manifest_rel,
                                               "paper_id": manifest.get("paper_id")}
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    record["hardware"] = jc.hardware(paths["cache"])
    record["models"] = {m: jc.verify_local_model(paths["models"], m, blobs=False)
                        for m in jc.MODELS}
    exam_dir = out / paper
    try:
        if not all(v["ok"] for v in record["models"].values()):
            raise RuntimeError("approved models are not prepared; run judge-host-prepare")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GAVEL_")}
        env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
                   GAVEL_AGY=str(paths["work"] / "no-agy" / "agy.exe"))
        with jc.OllamaServer(paths, out / "ollama-serve.log") as server:
            record["ollama_version"] = server.version
            record["tags"] = server.tags()
            exam = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", "-m", "gavel", "exam",
                 "--manifest", manifest_rel, "--out", str(exam_dir),
                 "--base-url", server.base_url, "--timeout", str(JUDGMENT_TIMEOUT_S)],
                cwd=jc.ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True)
        (out / "exam.stdout").write_bytes(exam.stdout)
        (out / "exam.stderr").write_bytes(exam.stderr)
        record["exam_exit"] = exam.returncode
        record["exam_meaning"] = EXAM_EXIT.get(exam.returncode, "unexpected")
        if exam.returncode not in (0, 3):
            problems.append(f"exam ended {record['exam_meaning']} (exit {exam.returncode})")
        committed_approved = jc.sha256_file(jc.ROOT / "approved-models.json")
        record["approved_models_sha256"] = committed_approved
        if (exam_dir / "results.json").is_file():
            problems.extend(approved_models_problems(exam_dir, committed_approved))
            verify = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", "-m", "gavel", "verify",
                 str(exam_dir / "receipts.jsonl"), "--content",
                 "--results", str(exam_dir / "results.json")],
                cwd=jc.ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                timeout=1800)
            (out / "verify.stdout").write_bytes(verify.stdout)
            (out / "verify.stderr").write_bytes(verify.stderr)
            record["verify_exit"] = verify.returncode
            if verify.returncode:
                problems.append("the exam's receipts do not verify")
        else:
            problems.append("the exam wrote no results.json")
    except Exception as exc:  # recorded, then the job fails
        problems.append(f"{type(exc).__name__}: {exc}")
    report = {}
    try:
        report = json.loads((exam_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    record["status"] = report.get("status")
    record["seconds"] = round(time.monotonic() - started, 1)
    record["problems"] = problems
    jc.write_json(out / "gavel-exam.json", record)
    lines = ["# gavel-exam (DRAFT workload)", "",
             f"Paper {record['paper_id']} ({paper}) on {paths['host']}: status "
             f"{record['status']}; job {'succeeded' if not problems else 'failed'}", "",
             f"- Ollama {record.get('ollama_version')}; manifest {manifest_rel}",
             f"- Re-attempted cells: {len(report.get('reattempted', []))}; cells without a "
             f"valid attempt: {len(report.get('gaps', {}).get('unresolved', []))}; cells "
             f"without records: {len(report.get('gaps', {}).get('missing', []))}",
             "- This paper is never dispatched again in round-3.", ""]
    lines += [f"- [{'ok' if b.get('ok') else 'NO'}] {b.get('bar')}: {b.get('detail')}"
              for b in report.get("bars", [])]
    lines += [f"- problem: {p}" for p in problems]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
