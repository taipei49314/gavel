"""gavel-verify: model-free verification of one exact gavel commit on the EC pool.

Entry of the gavel-verify workload declared in ec-workloads.json. It runs only
through the human-approved EC pool workload (EC POLICY independent-repos and
workload): EC fetches the exact commit, runs this file with the pool
generation's pinned Python in an environment built from scratch, and publishes
out/ as a private receipt ref. It never calls a model, Ollama, agy or codex;
it publishes nothing and changes no host setting.

Steps, each logged with its command, exit code, duration and output hashes:

1. Identity: the EC workload variables, repository, workload name and exact
   source SHA, and a clean checkout. It refuses to run on the two work
   machines (EC POLICY work-machine-local).
2. Dependencies: the six pure-Python pytest wheels pinned by sha256 in the
   committed uv.lock, installed with pip --require-hashes --no-deps into a
   venv in the job's work directory. That download from
   files.pythonhosted.org is the only network access. gavel itself declares no
   runtime dependency (pyproject.toml), which is checked.
3. The full test suite (tests/) with a JUnit report. Any failure, error or
   skip, or zero tests, fails the run.
4. `gavel verify --content` on every committed receipts file (*.jsonl).
5. round2.py twice, in separate processes, at PYTHONHASHSEED 1 and 17: it
   rebuilds every round-2 prompt from the case files and regenerates the
   round-2 tables from the committed receipts, once as locked (first attempt
   of every cell, attempt cap 1) and once as reported (evaluate() as of
   d0cb1dc, last receipt per cell wins). Every prompt must match and the two
   outputs must be byte-identical. The table contents are reported as
   observations; they do not decide the result.
6. The source SHA and a clean checkout again.

Steps 1-5 share a 25-minute budget (the entry allows 30): each step's timeout
is cut to what is left, and a step that would start after the budget is
spent is skipped and recorded as a problem, so result.json and SUMMARY.md
are always written. The step-6 checks get one more minute of their own.

Writes out/result.json, out/SUMMARY.md, out/suite.xml, out/logs/ and
out/round2/seed-<n>/.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPOSITORY = "taipei49314/gavel"
WORKLOAD = "gavel-verify"
WORK_MACHINES = frozenset({"LAPTOP-01AGNPJU", "LAPTOP-16NUA5I8"})
DEPENDENCIES = {"pytest", "colorama", "iniconfig", "packaging", "pluggy", "pygments"}
WHEEL_HOST = "https://files.pythonhosted.org/packages/"
SEEDS = ("1", "17")
# The declared entry allows 30 minutes (timeout_minutes). The steps share a
# 25-minute budget, so that result.json and SUMMARY.md are always written
# before EC ends the job: each step's timeout is cut to what is left, and a
# step that would start after the budget is spent is skipped and recorded.
# The two final git checks (step 6) get one more minute of their own, so a
# spent budget does not also hide whether the checkout changed.
TIME_BUDGET_SECONDS = 25 * 60
FINAL_CHECKS_SECONDS = 60
COMMITTED_RECEIPTS = frozenset({
    "attack/round-1/receipts.jsonl",
    "results/round-0/receipts-rerun-LWR1.jsonl",
    "results/round-0/receipts.jsonl",
    "results/round-1/receipts.jsonl",
    "results/round-2/regression/receipts.jsonl",
    "results/round-2/sealed/receipts.jsonl",
})
ROUND2_RECEIPTS = 149  # 110 regression + 39 sealed receipts, as committed at d0cb1dc


class Refused(RuntimeError):
    """This is not the approved workload, or not a pool host; nothing ran."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity() -> tuple[str, str, Path, Path]:
    for key in ("EC_WORKLOAD_SOURCE", "EC_WORKLOAD_OUT", "EC_WORKLOAD_WORK", "EC_WORKLOAD_SHA"):
        if not os.environ.get(key):
            raise Refused("run only through the approved EC pool workload")
    if (os.environ.get("EC_WORKLOAD_REPOSITORY") != REPOSITORY
            or os.environ.get("EC_WORKLOAD_NAME") != WORKLOAD
            or Path(os.environ["EC_WORKLOAD_SOURCE"]).resolve() != ROOT):
        raise Refused("unexpected workload identity")
    host = os.environ.get("COMPUTERNAME", "").upper()
    if not host or host in WORK_MACHINES or platform.node().upper() in WORK_MACHINES:
        raise Refused("gavel-verify runs only on an EC pool host, never on a work machine")
    expected = os.environ["EC_WORKLOAD_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise Refused("an exact 40-character source SHA is required")
    return (expected, host, Path(os.environ["EC_WORKLOAD_OUT"]).resolve(),
            Path(os.environ["EC_WORKLOAD_WORK"]).resolve())


def lock_requirements(lock_bytes: bytes) -> list[str]:
    """pip requirement lines for the six pytest wheels, from uv.lock hashes."""
    packages = tomllib.loads(lock_bytes.decode("utf-8"))["package"]
    selected = [p for p in packages if p["name"] in DEPENDENCIES]
    if {p["name"] for p in selected} != DEPENDENCIES or len(selected) != len(DEPENDENCIES):
        raise ValueError("uv.lock does not hold exactly the six expected packages")
    lines = []
    for package in sorted(selected, key=lambda p: p["name"]):
        wheels = package.get("wheels", [])
        if len(wheels) != 1 or not wheels[0]["url"].endswith("-none-any.whl"):
            raise ValueError(f"{package['name']}: expected one pure-Python wheel")
        wheel = wheels[0]
        if not wheel["url"].startswith(WHEEL_HOST):
            raise ValueError(f"{package['name']}: unexpected wheel host")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", wheel["hash"]):
            raise ValueError(f"{package['name']}: expected a sha256 wheel hash")
        lines.append(f"{package['name']} @ {wheel['url']} --hash={wheel['hash']}")
    return lines


def tree_files(base: Path) -> dict[str, bytes]:
    return {p.relative_to(base).as_posix(): p.read_bytes()
            for p in sorted(base.rglob("*")) if p.is_file()}


def main() -> int:
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    try:
        expected, host, out, work = identity()
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    logs.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               # No daemon and no agy: any accidental call fails closed.
               GAVEL_OLLAMA="http://127.0.0.1:9", GAVEL_AGY=str(work / "no-agy" / "agy.exe"))
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "GAVEL_TIMEOUT", "GAVEL_APPROVED_MODELS",
                 "PYTHONHASHSEED"):
        env.pop(name, None)
    steps: list[dict] = []
    problems: list[str] = []

    def run(name: str, command: list[str], *, seed: str = "1", timeout: int = 300,
            final: bool = False):
        limit = deadline + (FINAL_CHECKS_SECONDS if final else 0)
        remaining = int(limit - time.monotonic())
        if remaining < 1:
            problems.append(f"time budget exhausted before {name}")
            steps.append({"name": name, "command": [Path(command[0]).name] + command[1:],
                          "exit_code": 2, "skipped": "time budget exhausted",
                          "pythonhashseed": seed})
            return 2, b"", b""
        timeout = max(1, min(timeout, remaining))
        started = time.monotonic()
        timed_out = False
        try:
            process = subprocess.run(command, cwd=ROOT, env=dict(env, PYTHONHASHSEED=seed),
                                     stdin=subprocess.DEVNULL, capture_output=True,
                                     timeout=timeout, check=False)
            code, stdout, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as exc:
            code, timed_out = 2, True
            stdout, stderr = exc.stdout or b"", exc.stderr or b""
        except OSError as exc:
            code, stdout, stderr = 2, b"", str(exc).encode("utf-8")
        (logs / f"{name}.stdout").write_bytes(stdout)
        (logs / f"{name}.stderr").write_bytes(stderr)
        steps.append({"name": name, "command": [Path(command[0]).name] + command[1:],
                      "exit_code": code, "elapsed_seconds": round(time.monotonic() - started, 3),
                      "timeout_seconds": timeout, "timed_out": timed_out, "pythonhashseed": seed,
                      "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr)})
        return code, stdout, stderr

    # 1. identity and a clean checkout
    code, source, _ = run("source", ["git", "rev-parse", "--verify", "HEAD"])
    actual = source.decode("ascii", "replace").strip()
    if code or actual != expected:
        problems.append("source SHA mismatch or unreadable source")
    code, status, _ = run("clean-source", ["git", "status", "--porcelain", "-z"])
    if code or status:
        problems.append("source checkout is not clean")

    # 2. dependencies
    lock_bytes = None
    requirements: list[str] = []
    runtime_dependencies = None
    if not problems:
        try:
            lock_bytes = (ROOT / "uv.lock").read_bytes()
            requirements = lock_requirements(lock_bytes)
            requirements_path = work / "requirements.txt"
            requirements_path.write_text("\n".join(requirements) + "\n", encoding="utf-8",
                                         newline="\n")
            (out / "requirements.txt").write_bytes(requirements_path.read_bytes())
            project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
            runtime_dependencies = project["project"].get("dependencies")
            if runtime_dependencies != []:
                problems.append("pyproject.toml declares runtime dependencies")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append(f"dependency lock or pyproject unusable: {exc}")
    python = work / "venv" / "Scripts" / "python.exe"
    if not problems:
        code, _, _ = run("venv", [sys.executable, "-I", "-B", "-m", "venv", str(work / "venv")])
        if code:
            problems.append("job-local venv creation failed")
    if not problems:
        code, _, _ = run("dependencies", [
            str(python), "-I", "-B", "-m", "pip", "install", "--isolated",
            "--disable-pip-version-check", "--no-cache-dir", "--no-deps", "--require-hashes",
            "--only-binary=:all:", "-r", str(work / "requirements.txt")], timeout=600)
        if code:
            problems.append("hash-pinned dependency installation failed")

    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    receipts_checked: list[dict] = []
    round2 = {"seeds": list(SEEDS), "identical": None, "differing": [], "files": {},
              "summary": None, "versions": None}
    if not problems:
        command = [str(python), "-X", "utf8", "-B"]

        # 3. the full test suite
        code, _, _ = run("suite", command + [
            "-m", "pytest", "tests", "-p", "no:cacheprovider", "-rs",
            "--basetemp", str(work / "pytest"), "--junitxml", str(out / "suite.xml")],
            timeout=1200)
        try:
            cases = ET.parse(out / "suite.xml").getroot().findall(".//testcase")
            counts = {"tests": len(cases),
                      "failures": sum(c.find("failure") is not None for c in cases),
                      "errors": sum(c.find("error") is not None for c in cases),
                      "skipped": sum(c.find("skipped") is not None for c in cases)}
        except (OSError, ET.ParseError) as exc:
            problems.append(f"JUnit report missing or unreadable: {exc}")
        if code or not counts["tests"] or any(counts[k] for k in ("failures", "errors", "skipped")):
            problems.append("suite failed, ran zero tests or skipped tests")

        # 4. every committed receipts file, offline, with content checks
        code, listed, _ = run("receipts-list", ["git", "ls-files", "-z", "--", "*.jsonl"])
        files = sorted(p for p in listed.decode("utf-8", "replace").split("\0") if p)
        if code or not COMMITTED_RECEIPTS <= set(files):
            problems.append("committed receipts files are missing from the checkout")
        for index, path in enumerate(files, 1):
            code, _, _ = run(f"verify-{index:02d}", command + [
                "-m", "gavel", "verify", "--content", path])
            receipts_checked.append({"path": path, "sha256": digest((ROOT / path).read_bytes()),
                                     "verify_exit": code})
            if code:
                problems.append(f"gavel verify --content failed: {path}")

        # 5. round-2 prompts and tables at two hash seeds
        outputs = {}
        for seed in SEEDS:
            target = out / "round2" / f"seed-{seed}"
            code, _, _ = run(f"round2-seed{seed}", command + [
                str(HERE / "round2.py"), "--out", str(target),
                "--work", str(work / "round2" / f"seed-{seed}")], seed=seed, timeout=600)
            if code:
                problems.append(f"round2.py failed at PYTHONHASHSEED={seed}")
            else:
                outputs[seed] = tree_files(target)
        if len(outputs) == len(SEEDS):
            first, second = (outputs[s] for s in SEEDS)
            round2["differing"] = sorted(name for name in set(first) | set(second)
                                         if first.get(name) != second.get(name))
            round2["identical"] = not round2["differing"]
            round2["files"] = {name: digest(data) for name, data in first.items()}
            if round2["differing"]:
                problems.append("round-2 outputs differ between hash seeds")
            try:
                summary = json.loads(first["round2.json"].decode("utf-8"))
                round2["summary"] = summary
                round2["versions"] = json.loads(first["versions.json"].decode("utf-8"))
                prompts = summary["prompts"]
                if prompts["checked"] != ROUND2_RECEIPTS or prompts["matched"] != prompts["checked"]:
                    problems.append(f"round-2 prompt rebuild: {prompts['matched']}/"
                                    f"{prompts['checked']} receipts match "
                                    f"(expected {ROUND2_RECEIPTS}/{ROUND2_RECEIPTS})")
            except (KeyError, ValueError) as exc:
                problems.append(f"round2.py summary unreadable: {exc}")

        # 6. nothing changed the source
        code, final, _ = run("final-source", ["git", "rev-parse", "--verify", "HEAD"],
                             timeout=30, final=True)
        if code or final.decode("ascii", "replace").strip() != expected:
            problems.append("verification changed the source SHA")
        code, status, _ = run("final-status", ["git", "status", "--porcelain", "-z"],
                              timeout=30, final=True)
        if code or status:
            problems.append("verification changed the source checkout")

    result = {
        "schema_version": 1, "workload": WORKLOAD, "repository": REPOSITORY,
        "requested_sha": expected, "actual_sha": actual, "host": host,
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "uv_lock_sha256": digest(lock_bytes) if lock_bytes is not None else None,
        "requirements": requirements, "runtime_dependencies": runtime_dependencies,
        "steps": steps, "suite": counts, "receipts_verified": receipts_checked,
        "round2": round2,
        "test_sources_sha256": {p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
                                for p in sorted((ROOT / "tests").rglob("*.py"))},
        "passed": not problems, "problems": problems,
        "limitations": [
            "one EC Windows pool host and its pinned Python; no cross-platform claim",
            "no model, Ollama, agy or codex ran; no judgment was reproduced",
            "round-0, round-1, attack round-1 and round-2 receipts were produced on a work "
            "machine and stay unaccepted; this run checks and re-evaluates them, it does not "
            "accept them",
        ],
    }
    with (out / "result.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    (out / "SUMMARY.md").write_text(summary_text(result, out), encoding="utf-8", newline="\n")
    return 1 if problems else 0


def summary_text(result: dict, out: Path) -> str:
    suite, round2 = result["suite"], result["round2"]
    verified = [r for r in result["receipts_verified"] if r["verify_exit"] == 0]
    lines = ["# gavel-verify", "",
             f"Result: {'PASS' if result['passed'] else 'FAIL'}", "",
             f"- Source: `{result['actual_sha']}` (requested `{result['requested_sha']}`), "
             f"host {result['host']}",
             f"- Suite: {suite['tests']} tests, {suite['failures']} failures, "
             f"{suite['errors']} errors, {suite['skipped']} skipped (suite.xml)",
             f"- `gavel verify --content`: {len(verified)}/{len(result['receipts_verified'])} "
             f"committed receipts files verified"]
    summary = round2.get("summary")
    if summary:
        prompts = summary["prompts"]
        lines.append(f"- Round-2 prompt rebuild: {prompts['matched']}/{prompts['checked']} "
                     f"receipts reproduce the recorded anchor and prompt")
    if round2.get("versions"):
        v = round2["versions"]
        lines.append(f"- Prompt v{v['prompt_version']} instruction header sha256 "
                     f"`{v['instruction_header_sha256']}`; anchor v{v['anchor_version']}; "
                     f"receipt v{v['receipt_version']}")
    lines.append(f"- Round-2 outputs at PYTHONHASHSEED {' and '.join(round2['seeds'])}: "
                 f"byte-identical: {round2['identical']}")
    if result["problems"]:
        lines += ["", "Problems:"] + [f"- {p}" for p in result["problems"]]
    lines += ["", "Scope: gavel's own test suite, offline verification of every committed "
              "receipts file, and re-evaluation of the committed round-2 receipts, on one EC "
              "pool host. No model, Ollama, agy or codex ran; no judgment was reproduced. The "
              "receipts of round-0, round-1, attack round-1 and round-2 were produced on a work "
              "machine and stay 「未驗收」 (not accepted); this run does not accept them.", ""]
    if summary:
        lines += ["---", "",
                  "The round-2 tables below are observations from round2.py (seed "
                  f"{round2['seeds'][0]} output); they do not decide the result above.", ""]
        try:
            tables = (out / "round2" / f"seed-{round2['seeds'][0]}" /
                      "TABLES.md").read_text(encoding="utf-8")
            lines.append(tables.replace("# Round-2 tables", "## Round-2 tables", 1))
        except OSError:
            lines.append("(TABLES.md unreadable)")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
