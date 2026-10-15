"""DRAFT, NOT FOR APPROVAL until the round-3 lock: run one round-3 paper on
LAPTOP-01AGNPJU.

Round-3 runs on LAPTOP-01AGNPJU under EC POLICY `gavel-pju-execution`
(docs/proposals/round-3-PREREG-DRAFT.md, section 2). This script takes the
place of the EC pool workload draft `gavel-exam` (workloads/gavel_exam/run.py)
on that host, without its pool-host checks, and enforces:

- the host is LAPTOP-01AGNPJU;
- the harness is the lock commit's: the lock commit (--lock-commit) is an
  ancestor of HEAD and already on origin, and every change since it is under
  results/round-3/ (run records only);
- the paper is one of the locked manifests in PAPERS; every arm uses the
  local transport "ollama", the manifest pins the Ollama version and fixes the
  options (gavel exam's preflight then checks the live version and digests);
- one run per paper: a paper that has a receipts file under
  results/round-3/<paper>/ is never run again. A run that ended before its
  first receipt (the preflight refused, or the daemon was unavailable) judged
  nothing, and the paper may run again into the next run-<k> directory;
- time anchors: before the exam, a start record (START.json) is committed and
  pushed; after it, the exam's outputs and the end record (RUN.json,
  SUMMARY.md) are committed and pushed. GitHub's push event times bound the
  run from both sides; the host clock is not an anchor;
- after the exam: `gavel verify --content --results`, and the committed
  approved-models.json is the file that gated the exam.

Exit 0 when the paper is PASS (bars) or COMPLETE (external scoring) and every
check passed; 1 when the exam ran but a check failed or the status is not
PASS/COMPLETE; 2 when it refused before the start record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "LAPTOP-01AGNPJU"
BASE_URL = "http://127.0.0.1:11434"
OLLAMA_VERSION = "0.40.4"
RESULTS = "results/round-3"
# DRAFT: the locked manifests, as repository paths, fixed at the round-3 lock.
PAPERS = {
    "R": "cases/round-3-R.manifest.json",
    "R-fast": "cases/round-3-R-fast.manifest.json",
    "K": "cases/round-3-K.manifest.json",
    "K-fast": "cases/round-3-K-fast.manifest.json",
}
JUDGMENT_TIMEOUT_S = None  # DRAFT: fixed at the lock from the pre-lock smoke timings
EXAM_EXIT = {0: "PASS", 1: "FAIL", 2: "INVALID_PAPER, INVALID_RECORDS, INCOMPLETE or refused",
             3: "COMPLETE"}


class Refused(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str, root: Path = ROOT) -> str:
    done = subprocess.run(["git", *args], cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True)
    if done.returncode:
        raise Refused(f"git {' '.join(args)} failed: "
                      f"{done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout.decode("utf-8").strip()


def check_host() -> str:
    host = os.environ.get("COMPUTERNAME") or socket.gethostname()
    if host.upper() != HOST:
        raise Refused(f"host {host!r} is not {HOST}")
    return HOST


def check_harness(lock_commit: str, root: Path = ROOT) -> dict:
    """The harness must be the lock commit's: the working tree clean
    (untracked files included, since a stray module could shadow the
    harness), the lock commit an ancestor of HEAD and contained in a remote
    branch, and every path changed since it under RESULTS."""
    if git("status", "--porcelain", root=root):
        raise Refused("the working tree has uncommitted or untracked files")
    lock = git("rev-parse", "--verify", f"{lock_commit}^{{commit}}", root=root)
    head = git("rev-parse", "HEAD", root=root)
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", lock, head], cwd=root,
                              stdin=subprocess.DEVNULL, capture_output=True)
    if ancestor.returncode:
        raise Refused(f"the lock commit {lock} is not an ancestor of HEAD {head}")
    if not git("branch", "-r", "--contains", lock, root=root):
        raise Refused(f"the lock commit {lock} is not on any remote branch (push it first)")
    changed = [p for p in git("diff", "--name-only", lock, head, root=root).splitlines() if p]
    outside = [p for p in changed if not p.startswith(RESULTS + "/")]
    if outside:
        raise Refused(f"files changed since the lock commit outside {RESULTS}/: {outside}")
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", root=root)
    if branch in ("main", "master"):
        raise Refused("run records are not pushed to main; check out a round-3 run branch")
    return {"lock_commit": lock, "head": head, "branch": branch}


def check_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_bytes().decode("utf-8"))
    arms = manifest.get("arms") or {}
    not_local = sorted(name for name, spec in arms.items() if spec.get("transport") != "ollama")
    if not_local:
        raise Refused(f"arms {not_local} are not local; the informed arm is excluded in round-3")
    if (manifest.get("runtime") or {}).get("ollama_version") != OLLAMA_VERSION:
        raise Refused(f"the manifest does not pin Ollama {OLLAMA_VERSION}")
    if not manifest.get("options"):
        raise Refused("the manifest does not fix the generation options")
    return manifest


def next_run(paper_dir: Path) -> int:
    """The number of the next run directory. Refuses when an earlier run of
    the paper wrote a receipts file: that chain is the paper's only record."""
    earlier = sorted(p for p in paper_dir.glob("run-*") if p.is_dir()) if paper_dir.is_dir() else []
    for run_dir in earlier:
        if (run_dir / "receipts.jsonl").exists():
            raise Refused(f"{run_dir.relative_to(paper_dir.parent)} holds receipts; "
                          f"a paper is run once in round-3")
    return len(earlier) + 1


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


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def commit_and_push(paths: list[Path], message: str, branch: str) -> str:
    git("add", "--", *[str(p.relative_to(ROOT)) for p in paths])
    git("commit", "-q", "-m", message)
    git("push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    return git("rev-parse", "HEAD")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paper", choices=sorted(PAPERS))
    parser.add_argument("--lock-commit", required=True)
    parser.add_argument("--commit-trailer", action="append", default=[],
                        help="a trailer line appended to the run-record commit messages")
    args = parser.parse_args(argv)
    trailer = ("\n\n" + "\n".join(args.commit_trailer)) if args.commit_trailer else ""
    manifest_rel = PAPERS[args.paper]
    paper_dir = ROOT / RESULTS / args.paper
    try:
        if JUDGMENT_TIMEOUT_S is None:
            raise Refused("DRAFT: the round-3 papers are not locked")
        host = check_host()
        git("fetch", "-q", "origin")
        harness = check_harness(args.lock_commit)
        manifest = check_manifest(ROOT / manifest_rel)
        run = next_run(paper_dir)
    except (Refused, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    run_dir = paper_dir / f"run-{run}"
    run_dir.mkdir(parents=True)
    rel_run = run_dir.relative_to(ROOT).as_posix()
    start = {"paper": args.paper, "paper_id": manifest.get("paper_id"), "run": run,
             "manifest": manifest_rel, "manifest_sha256": sha256_file(ROOT / manifest_rel),
             "runner": "tools/round3_run.py", "runner_sha256": sha256_file(Path(__file__)),
             "lock_commit": harness["lock_commit"], "host": host,
             "host_clock_utc": utc_now(), "out": rel_run,
             "timeout_s": JUDGMENT_TIMEOUT_S, "ollama_version": OLLAMA_VERSION,
             "label": "human-authorized local PJU, NOT EC pool"}
    try:
        write_json(run_dir / "START.json", start)
        start_commit = commit_and_push(
            [run_dir / "START.json"],
            f"round-3: start paper {args.paper} run {run} (lock {harness['lock_commit'][:12]})"
            + trailer, harness["branch"])
    except Refused as exc:
        print(f"REFUSED: the start record was not pushed: {exc}", file=sys.stderr)
        return 2

    env = {k: v for k, v in os.environ.items() if not k.startswith("GAVEL_")}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
               GAVEL_AGY=str(ROOT / "no-agy" / "agy.exe"))
    problems, record = [], dict(start, start_commit=start_commit)
    started = time.monotonic()
    exam = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "gavel", "exam",
         "--manifest", manifest_rel, "--out", rel_run,
         "--base-url", BASE_URL, "--timeout", str(JUDGMENT_TIMEOUT_S)],
        cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True)
    (run_dir / "exam.stdout.txt").write_bytes(exam.stdout)
    (run_dir / "exam.stderr.txt").write_bytes(exam.stderr)
    record["exam_exit"] = exam.returncode
    record["exam_meaning"] = EXAM_EXIT.get(exam.returncode, "unexpected")
    if exam.returncode not in (0, 3):
        problems.append(f"exam ended {record['exam_meaning']} (exit {exam.returncode})")
    committed_approved = sha256_file(ROOT / "approved-models.json")
    record["approved_models_sha256"] = committed_approved
    if (run_dir / "results.json").is_file():
        problems.extend(approved_models_problems(run_dir, committed_approved))
        verify = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-m", "gavel", "verify",
             f"{rel_run}/receipts.jsonl", "--content", "--results", f"{rel_run}/results.json"],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True)
        (run_dir / "verify.stdout.txt").write_bytes(verify.stdout)
        (run_dir / "verify.stderr.txt").write_bytes(verify.stderr)
        record["verify_exit"] = verify.returncode
        if verify.returncode:
            problems.append("the exam's receipts do not verify")
    else:
        problems.append("the exam wrote no results.json")
    report = {}
    try:
        report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    record["status"] = report.get("status")
    record["seconds"] = round(time.monotonic() - started, 1)
    record["host_clock_end_utc"] = utc_now()
    record["problems"] = problems
    write_json(run_dir / "RUN.json", record)
    receipts = run_dir / "receipts.jsonl"
    lines = [f"# Round-3 paper {args.paper}, run {run}", "",
             f"Paper {record['paper_id']} on {host}: status {record['status']}; "
             f"{'all checks passed' if not problems else 'checks failed'}.",
             "Label: human-authorized local PJU, NOT EC pool.", "",
             f"- Lock commit {harness['lock_commit']}; start record {start_commit}",
             f"- Ollama {OLLAMA_VERSION}; manifest {manifest_rel}; timeout {JUDGMENT_TIMEOUT_S} s",
             f"- Re-attempted cells: {len(report.get('reattempted', []))}; cells without a "
             f"valid attempt: {len(report.get('gaps', {}).get('unresolved', []))}; cells "
             f"without records: {len(report.get('gaps', {}).get('missing', []))}",
             ("- Receipts were written: this paper is never run again in round-3."
              if receipts.exists() else
              "- No receipt was written: nothing was judged, and the paper may run again."), ""]
    lines += [f"- [{'ok' if b.get('ok') else 'NO'}] {b.get('bar')}: {b.get('detail')}"
              for b in report.get("bars", [])]
    lines += [f"- problem: {p}" for p in problems]
    (run_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    outputs = sorted(p for p in run_dir.iterdir() if p.is_file() and p.name != "START.json")
    try:
        commit_and_push(outputs,
                        f"round-3: end paper {args.paper} run {run}: status {record['status']}"
                        + trailer, harness["branch"])
    except Refused as exc:
        problems.append(f"the end record was not pushed: {exc}")
        print(f"END RECORD NOT PUSHED: {exc}", file=sys.stderr)
    print("\n".join(lines))
    return 0 if not problems and record["status"] in ("PASS", "COMPLETE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
