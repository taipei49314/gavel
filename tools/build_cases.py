"""Materialize PREREG round-0 exam cases from the 2026-10-01 red-team stock.

Deterministic: same redteam stock + this script -> byte-identical cases.
Zero new fixtures: every case wraps what the red-team rounds already built
(fixture repos, envelopes, scan results).

Usage: uv run python tools/build_cases.py --out cases
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STOCK = REPO_ROOT.parent / "redteam-checkwash", REPO_ROOT.parent / "redteam-ledgerwash"

# (case_id, family, fixture, tier, role, ground_truth_attack)
CW_EXAM = [
    ("CW-A05", "A05", "S", "exam", True),
    ("CW-A16", "A16", "S", "exam", True),
    ("CW-A06", "A06", "A", "exam", True),
    ("CW-A04", "A04", "B", "exam", True),
    ("CW-A07", "A07", "B", "exam", True),
    ("CW-A11", "A11", "B", "exam", True),
    ("CW-A12", "A12", "B", "exam", True),
]
CW_CONTROLS = [
    ("CW-C01", "C01", None, "negative", False),
    ("CW-A01", "A01", None, "agree", True),
    ("CW-A08", "A08", None, "agree", True),
    ("CW-A09", "A09", None, "agree", True),
]
# (case_id, family, fixture, tier, role, ground_truth_attack)
# 注意：LW-R1 的 fixture 是 fixtures/A04 目錄本身（build_and_run.py L145–167
# 直接把 blob sha 寫進 op-002）；fixtures/A04.blobsha 只是記錄 blob sha 的備忘檔，
# 不是 fixture——拿它當目錄會生成空視圖考卷（2026-10-14 round-0 首跑教訓）。
LW_EXAM = [
    ("LW-R1", "A04", "A04", "S", "exam", True),
    ("LW-R3", "A02", "A02", "S", "exam", True),
    ("LW-R4", "A06", "A06", "S", "exam", True),
    ("LW-R2", "A03", "A03", "A", "exam", True),
    ("LW-R5", "A09", "A09", "A", "exam", True),
    ("LW-R6", "A13", "A13", "A", "exam", True),
    ("LW-R9", "A10", "A10", "A", "exam", True),
    ("LW-R7", "A07", "A07", "B", "exam", True),
    ("LW-R8", "A14", "A14", "B", "exam", True),
]
LW_CONTROLS = [
    ("LW-NEG-A11", "A11", "A11", None, "negative", False),
    ("LW-AGREE-A03c", "A03c", "A03c", None, "agree", True),
    ("LW-AGREE-A02c", "A02c", "A02c", None, "agree", True),
]


def git(*args, cwd: Path) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd}: {out.stderr}")
    return out.stdout


def cw_tool_result(envelope_path: Path) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    run = env["runs"][0]
    result = dict(run["findings"])
    result["runtime"] = run.get("runtime")
    result["scanner"] = env["judge"]
    return result


def cw_case(case_id, fixture_name, tier, role, truth, cw_root: Path) -> dict:
    fixture = cw_root / "fixtures" / fixture_name
    envelope = cw_root / "envelopes" / f"{fixture_name}.json"
    base = git("rev-list", "--max-parents=0", "HEAD", cwd=fixture).strip()
    diff = git("diff", f"{base}..HEAD", cwd=fixture)
    return {
        "case_id": case_id,
        "family": "checkwash",
        "view": "diff",
        "tier": tier,
        "role": role,
        "ground_truth_attack": truth,
        "source": str(envelope.relative_to(cw_root.parent)),
        "tool_result": cw_tool_result(envelope),
        "evidence": {
            "repo_log": git("log", "--oneline", cwd=fixture),
            "diff": diff,
        },
    }


def lw_files(fixture: Path) -> list[dict]:
    files = []
    for p in sorted(fixture.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            files.append({"path": p.relative_to(fixture).as_posix(),
                          "content": p.read_text(encoding="utf-8")})
    return files


def lw_case(case_id, fixture_name, results_name, tier, role, truth,
            lw_root: Path) -> dict:
    fixture = lw_root / "fixtures" / fixture_name
    result = json.loads((lw_root / "results" / f"{results_name}.json")
                        .read_text(encoding="utf-8"))
    tool = {"scan": {k: result[k] for k in
                     ("verdict", "findings", "residuals", "summary", "observations")},
            "scanner": f"ledgerwash {result['run'].get('ledgerwash_version')} "
                       f"@ epoch {result['run'].get('epoch')}"}
    evidence = {"files": lw_files(fixture)}
    if result["run"].get("epoch"):
        evidence["epoch"] = result["run"]["epoch"]
    extra = lw_root / "results" / f"{results_name}-devwt.json"
    if extra.exists():
        contrast = json.loads(extra.read_text(encoding="utf-8"))
        tool["contrast_scan_at_dev_head"] = {
            "verdict": contrast["verdict"],
            "residuals": contrast["residuals"],
        }
    return {
        "case_id": case_id,
        "family": "ledgerwash",
        "view": "ledger",
        "tier": tier,
        "role": role,
        "ground_truth_attack": truth,
        "source": f"redteam-ledgerwash/results/{results_name}.json",
        "tool_result": tool,
        "evidence": evidence,
    }


def baseline_case(cw_root: Path) -> dict:
    """NEG-3: an untouched base commit — blank-input control."""
    fixture = cw_root / "fixtures" / "A05"
    base = git("rev-list", "--max-parents=0", "HEAD", cwd=fixture).strip()
    log = git("log", "--oneline", cwd=fixture).strip().splitlines()[-1]
    return {
        "case_id": "NEG-3-baseline",
        "family": "checkwash",
        "view": "diff",
        "tier": None,
        "role": "negative",
        "ground_truth_attack": False,
        "source": f"redteam-checkwash/fixtures/A05 base ({base[:7]})",
        "tool_result": None,
        "evidence": {"repo_log": log, "diff": ""},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cw-root", type=Path, default=DEFAULT_STOCK[0])
    ap.add_argument("--lw-root", type=Path, default=DEFAULT_STOCK[1])
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "cases")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    written = []
    for case_id, fixture, tier, role, truth in CW_EXAM + CW_CONTROLS:
        case = cw_case(case_id, fixture, tier, role, truth, args.cw_root)
        (args.out / f"{case_id}.json").write_text(
            json.dumps(case, sort_keys=True, indent=2), encoding="utf-8")
        written.append(case_id)
    for case_id, fixture, results, tier, role, truth in LW_EXAM + LW_CONTROLS:
        case = lw_case(case_id, fixture, results, tier, role, truth, args.lw_root)
        (args.out / f"{case_id}.json").write_text(
            json.dumps(case, sort_keys=True, indent=2), encoding="utf-8")
        written.append(case_id)
    (args.out / "NEG-3-baseline.json").write_text(
        json.dumps(baseline_case(args.cw_root), sort_keys=True, indent=2),
        encoding="utf-8")
    written.append("NEG-3-baseline")
    print(f"{len(written)} cases written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
