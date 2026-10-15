"""gavel-verify helper: rebuild the round-2 prompts and regenerate the round-2
tables from the committed receipts. Model-free.

It runs only inside the gavel-verify EC pool workload: run.py starts it twice,
at two PYTHONHASHSEED values, each time with a fresh --out and --work, and
compares the two outputs byte for byte. It imports gavel; it never calls
Ollama, agy or any model, and it writes only under --out and --work.

The round-2 receipts were produced on a work machine and stay 「未驗收」
(not accepted). This helper re-reads and re-evaluates them; it reproduces no
judgment.

Written under --out (UTF-8, LF, no absolute paths and no clock times, so two
runs must be byte-identical):

  versions.json          harness, prompt, anchor and receipt versions and the
                         sha256 of the prompt v4 instruction header
  papers.json            per paper: case count, materialized manifest sha256,
                         receipts file sha256 and count
  prompts/<paper>.json   for every receipt: do render_case_v1(case file) and
                         the prompt v4 header reproduce the anchor and prompt
                         that the receipt recorded (text and sha256)
  as-locked/             the locked contract (PREREG Addendum 4 and 5): the
                         first attempt of every cell only, attempt cap 1,
                         because round-2 registered no re-attempts; later
                         attempts are listed and not counted. The same
                         contract over every receipt is also written; it shows
                         each attempt beyond the cap as a record error.
  as-reported/           gavel.qualify.evaluate as of d0cb1dc over every
                         receipt (a later receipt for a cell replaces an
                         earlier one) with the as-run arguments, compared byte
                         for byte with the committed report.json; for the
                         sealed paper also the computed rows of the as-run
                         scoring.md script, compared with the committed file
  TABLES.md              a readable overview of both views
  round2.json            the summary that run.py reads
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for entry in (str(HERE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from gavel import __version__ as HARNESS_VERSION  # noqa: E402
from gavel.anchor import ANCHOR_VERSION, render_case_v1, sha256_text  # noqa: E402
from gavel.prompt import (INSTRUCTION_HEADER, MECHANISM_CLASSES,  # noqa: E402
                          PROMPT_VERSION, render_prompt)
from gavel.qualify import (evaluate, load_paper, records_from_receipts,  # noqa: E402
                           runs_for)
from gavel.receipts import RECEIPT_VERSION, verify_file  # noqa: E402
from gavel.sealed import parse_answer_key_markdown, score_sealed  # noqa: E402

import legacy_round2  # noqa: E402

SPEC = HERE / "round2_papers.json"
PROMPT_CHECKS = ("anchor_sha256", "prompt_sha256", "anchor_text", "prompt_text")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def versions() -> dict:
    return {"harness_version": HARNESS_VERSION, "prompt_version": PROMPT_VERSION,
            "anchor_version": ANCHOR_VERSION, "receipt_version": RECEIPT_VERSION,
            "instruction_header_sha256": sha256_text(INSTRUCTION_HEADER),
            "mechanism_classes": list(MECHANISM_CLASSES)}


def materialize(paper: dict, work: Path) -> tuple[Path, dict]:
    """Copy the paper's case files next to its manifest under work, then load
    the paper with gavel.qualify.load_paper, which checks every case file's
    sha256, case_id, tier and role and that it renders."""
    manifest = paper["manifest"]
    target = work / "papers" / manifest["paper_id"]
    target.mkdir(parents=True)
    for case in manifest["cases"]:
        shutil.copyfile(ROOT / paper["source_dir"] / case["path"], target / case["path"])
    manifest_path = target / "manifest.json"
    write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest_path, load_paper(manifest_path)


def rebuild_prompts(loaded: dict, receipts: list) -> dict:
    """Re-render every receipt's anchor (frozen v1 renderer) and prompt (v4)."""
    rows = []
    for index, rec in enumerate(receipts, 1):
        row = {"receipt": index, "case_id": rec["case_id"], "arm": rec["arm"],
               "run": rec.get("run", 1)}
        case = loaded["cases"].get(rec["case_id"])
        if case is None:
            row["error"] = "case_id is not in the paper"
        else:
            anchor = render_case_v1(case)
            prompt = render_prompt(anchor)
            row["anchor_sha256"] = sha256_text(anchor) == rec["anchor_sha256"]
            row["prompt_sha256"] = sha256_text(prompt) == rec["prompt_sha256"]
            row["anchor_text"] = anchor == rec.get("anchor_text")
            row["prompt_text"] = prompt == rec.get("prompt_text")
        row["match"] = "error" not in row and all(row[k] is True for k in PROMPT_CHECKS)
        rows.append(row)
    return {"checked": len(rows), "matched": sum(1 for r in rows if r["match"]),
            "mismatched": [r for r in rows if not r["match"]], "receipts": rows}


def outcome(record: dict) -> str:
    verdict = record.get("verdict")
    if isinstance(verdict, dict) and not record.get("unaudited"):
        text = str(verdict.get("verdict"))
        if text == "attack":
            text += f" ({verdict.get('mechanism_class')})"
        return text
    return f"UNAUDITED: {record.get('unaudited')}"


def observations_md(manifest: dict, first: list, excluded: list, status: str) -> str:
    """First-attempt verdicts per cell, unscored."""
    cell = {(r["case_id"], r["arm"], r["run"]): r for r in first}
    columns, heads = [], []
    for arm, spec in manifest["arms"].items():
        top = max(runs_for(spec, case["tier"]) for case in manifest["cases"])
        for run in range(1, top + 1):
            columns.append((arm, run))
            heads.append(arm if top == 1 else f"{arm} run {run}")
    out = [f"# {manifest['paper_id']}: first-attempt observations (not scored)", "",
           "Each cell is the first recorded attempt for that case, arm and run, as the "
           "locked contract counts it (attempt cap 1). Status under that contract: "
           f"{status}. These are observations only; nothing here is a score.", "",
           "| case | tier | role | " + " | ".join(heads) + " |",
           "|---|---|---|" + "---|" * len(heads)]
    for case in manifest["cases"]:
        cells = []
        for arm, run in columns:
            in_matrix = run <= runs_for(manifest["arms"][arm], case["tier"])
            record = cell.get((case["case_id"], arm, run))
            text = outcome(record) if record is not None else ("no record" if in_matrix else "-")
            cells.append(" ".join(text.split()).replace("|", "\\|"))
        out.append(f"| {case['case_id']} | {case['tier'] or '-'} | {case['role']} | "
                   + " | ".join(cells) + " |")
    out += ["", "## Later attempts (recorded, not counted under the locked contract)", ""]
    if excluded:
        out += [f"- receipt {e['receipt']}: {e['case_id']} {e['arm']} run {e['run']} attempt "
                f"{e['attempt']}: {e['outcome']}" for e in excluded]
    else:
        out.append("- none")
    return "\n".join(out) + "\n"


def as_locked(paper: dict, manifest: dict, receipts: list, out: Path, key) -> dict:
    pid = manifest["paper_id"]
    records = records_from_receipts(receipts, legacy_attempts=True)
    first = [r for r in records if r["attempt"] == 1]
    excluded = [{"receipt": index, "case_id": r["case_id"], "arm": r["arm"], "run": r["run"],
                 "attempt": r["attempt"], "outcome": outcome(r),
                 "execution_note": (receipts[index - 1].get("execution") or {}).get("note")}
                for index, r in enumerate(records, 1) if r["attempt"] > 1]
    first_report = evaluate(manifest, first)
    whole_report = evaluate(manifest, records)
    base = out / "as-locked"
    write_json(base / f"{pid}.first-attempt.report.json", first_report)
    write_json(base / f"{pid}.every-receipt.report.json", whole_report)
    write_json(base / f"{pid}.later-attempts.json", excluded)
    write_text(base / f"{pid}.observations.md",
               observations_md(manifest, first, excluded, first_report["status"]))
    gaps = sorted([list(c) for c in first_report["gaps"]["missing"]]
                  + [list(g["cell"]) for g in first_report["gaps"]["unresolved"]])
    expected = sorted(list(g) for g in paper["expected_first_pass_gaps"])
    result = {"first_attempt_status": first_report["status"], "first_attempt_gaps": gaps,
              "expected_first_pass_gaps": expected,
              "matches_status_of_record": first_report["status"] == "INCOMPLETE" and gaps == expected,
              "every_receipt_status": whole_report["status"],
              "every_receipt_errors": len(whole_report["errors"]),
              "later_attempts": len(excluded)}
    if key is not None:
        score = score_sealed(manifest, key, first)
        write_json(base / f"{pid}.sealed-observations.json", score)
        result["sealed_status"] = score["status"]
        result["sealed_scored"] = score["scored"]
    return result


def as_reported(paper: dict, receipts: list, out: Path, key_text, pairs) -> dict:
    pid = paper["manifest"]["paper_id"]
    cases = legacy_round2.json_load_all(ROOT / paper["source_dir"])
    committed_results = json.loads((ROOT / paper["committed_results"]).read_bytes().decode("utf-8"))
    expected = {tuple(t) for t in committed_results["manifest"]}
    args = paper["legacy_as_run"]
    report = legacy_round2.evaluate(cases, receipts, expected=expected,
                                    tier_counts=dict(args["tier_counts"]), a_min=args["a_min"])
    text = legacy_round2.report_text(report)
    base = out / "as-reported"
    write_text(base / f"{pid}.report.json", text)
    committed = (ROOT / paper["committed_report"]).read_bytes()
    result = {"status": report["status"],
              "report_bytes_equal": text.encode("utf-8") == committed,
              "report_equal": report == json.loads(committed.decode("utf-8")),
              "fast_arm_divergence": report.get("fast_arm_divergence"),
              "informed_arm_divergence": report.get("informed_arm_divergence")}
    if key_text is not None:
        rows, lines = legacy_round2.sealed_scoring_rows(key_text, receipts, pairs)
        committed_lines = (ROOT / paper["committed_scoring"]).read_bytes().decode("utf-8").split("\n")
        committed_rows = [line for line in committed_lines if line.startswith("| SP-")]
        committed_arms = [line for line in committed_lines
                          if line.startswith(("- primary:", "- fast:", "- informed:"))]
        result["scoring_rows_equal"] = rows == committed_rows
        result["scoring_arm_lines_equal"] = lines == committed_arms
        result["scoring_lines_not_computed"] = [line for line in committed_lines
                                                if line.startswith("- ") and line not in committed_arms]
        table = ["| case | truth | primary | fast | informed | pair |",
                 "|---|---|---|---|---|---|"] + rows + [""] + lines
        write_text(base / f"{pid}.scoring-rows.md", "\n".join(table) + "\n")
    return result


def yes(value) -> str:
    return "yes" if value else "NO"


def tables_md(summary: dict) -> str:
    papers = summary["papers"]
    out = ["# Round-2 tables regenerated from the committed receipts", "",
           f"Generated by workloads/gavel_verify/round2.py with gavel {HARNESS_VERSION}; no model "
           "was called. The round-2 receipts were produced on a work machine and stay "
           "「未驗收」 (not accepted): this re-reads and re-evaluates them and reproduces no "
           "judgment.", "",
           "## Prompt rebuild", "",
           f"{summary['prompts']['matched']}/{summary['prompts']['checked']} receipts: the frozen "
           "anchor v1 renderer and the prompt v4 header reproduce the recorded anchor and "
           "prompt (text and sha256).", "",
           "## As locked (PREREG Addendum 4 and 5: first attempt of every cell, attempt cap 1)", "",
           "| paper | status | cells without a valid first attempt | later attempts not counted "
           "| matches the status of record (D1) | every receipt under the same contract |",
           "|---|---|---|---|---|---|"]
    for pid, item in papers.items():
        locked = item["as_locked"]
        gaps = ", ".join("/".join(map(str, g)) for g in locked["first_attempt_gaps"]) or "none"
        out.append(f"| {pid} | {locked['first_attempt_status']} | {gaps} | "
                   f"{locked['later_attempts']} | {yes(locked['matches_status_of_record'])} | "
                   f"{locked['every_receipt_status']} ({locked['every_receipt_errors']} record "
                   f"error(s)) |")
    out += ["", "## As reported (gavel.qualify.evaluate at d0cb1dc, last receipt per cell "
            "wins, as-run arguments)", "",
            "| paper | status | committed report.json reproduced byte for byte | "
            "fast divergence | informed divergence |",
            "|---|---|---|---|---|"]
    for pid, item in papers.items():
        reported = item["as_reported"]
        out.append(f"| {pid} | {reported['status']} | {yes(reported['report_bytes_equal'])} | "
                   f"{reported.get('fast_arm_divergence')} | "
                   f"{reported.get('informed_arm_divergence')} |")
        if "scoring_rows_equal" in reported:
            out += ["", f"{pid} scoring.md: computed table rows reproduced: "
                        f"{yes(reported['scoring_rows_equal'])}; per-arm lines reproduced: "
                        f"{yes(reported['scoring_arm_lines_equal'])}. Lines that were literal "
                        f"text in the as-run script (not computed, not reproduced):"]
            out += [f"- `{line}`" for line in reported["scoring_lines_not_computed"]]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="fresh output directory")
    parser.add_argument("--work", required=True, help="fresh scratch directory")
    args = parser.parse_args(argv)
    out, work = Path(args.out), Path(args.work)
    out.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    spec = json.loads(SPEC.read_bytes().decode("utf-8"))
    summary = {"schema_version": 1, "prompts": {"checked": 0, "matched": 0}, "papers": {}}
    papers_info = {}
    write_json(out / "versions.json", versions())
    for paper in spec["papers"]:
        _, loaded = materialize(paper, work)
        manifest = loaded["manifest"]
        pid = manifest["paper_id"]
        receipts_path = ROOT / paper["receipts"]
        receipts = verify_file(receipts_path, MECHANISM_CLASSES, content=True)
        papers_info[pid] = {"cases": len(manifest["cases"]),
                            "manifest_sha256": loaded["manifest_sha256"],
                            "receipts_file": paper["receipts"],
                            "receipts_sha256": file_sha256(receipts_path),
                            "receipts": len(receipts),
                            "receipt_versions": sorted({r["receipt_version"] for r in receipts})}
        prompts = rebuild_prompts(loaded, receipts)
        write_json(out / "prompts" / f"{pid}.json", prompts)
        summary["prompts"]["checked"] += prompts["checked"]
        summary["prompts"]["matched"] += prompts["matched"]
        key = key_text = pairs = None
        if paper.get("answer_key"):
            key_text = (ROOT / paper["answer_key"]).read_bytes().decode("utf-8")
            key = parse_answer_key_markdown(key_text)
            pairs = key["pairs"]
        summary["papers"][pid] = {
            "as_locked": as_locked(paper, manifest, receipts, out, key),
            "as_reported": as_reported(paper, receipts, out, key_text, pairs),
        }
    write_json(out / "papers.json", papers_info)
    write_text(out / "TABLES.md", tables_md(summary))
    write_json(out / "round2.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
