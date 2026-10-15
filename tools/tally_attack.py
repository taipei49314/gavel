"""Generate the attack-round reconciliation table from locked sources (v2).

Reads the evaluator's PREREG (predictions) and a receipts file (outcomes)
and emits the reconciliation table. This exists because hand-written
reconciliation drifts: the round-1 report quoted a chat summary instead of
the locked PREREG and mis-stated ATK-005 (see REPORT ERRATUM). Predictions,
outcomes and hit-rates must come from bytes, not prose.

v2 (takeover audit 2026-10-15, CR-12 and F10):
- Outcomes are read from schema-v2 verdicts (verdict, mechanism_class,
  offending_element). Schema-v1 verdicts ({"attack": true|false, ...}, as in
  attack/round-1/receipts.jsonl) are still read, as attack or clean. v1 read
  every v2 verdict as "no outcome".
- Receipts are verified (gavel.receipts.verify_file, with content checks)
  and resolved by the first-valid-attempt rule (gavel.qualify.resolve_slots);
  v1 kept the last receipt per (case, arm). v1/v2 receipts are numbered by
  file order. A broken attempt protocol (an attempt after a valid one, a
  duplicate, a gap) stops the tool with exit 2 and no table.
- Two hit counts per arm, each with a Wilson 95% interval (PREREG-codex
  asks for one whenever rates are published): the attack boolean alone (the
  round-1 convention), and the boolean plus the exact predicted
  mechanism_class (closer to PREREG-codex's "Prediction held"). Whether the
  offending element names the actual reduction needs a reader: it is
  printed, never scored.
- UNAUDITED and missing outcomes are shown as such and never count as held.
- "gate released" follows `gavel scan`'s exit rule (gavel.cli.scan_exit_code):
  every arm with a receipt for the case returned a valid clean verdict and
  the required arms primary and fast are among them.
- Every summary line is computed from the inputs; --out is never
  overwritten.

Usage:
  python tools/tally_attack.py --prereg <PREREG-codex.md> \
      --receipts <receipts.jsonl> [--out <table.md>]
Exit codes: 0 table written or printed; 2 inputs unreadable or unverifiable,
broken attempt protocol, or --out already exists.
"""

import argparse
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gavel.cli import SCAN_REQUIRED_ARMS, scan_exit_code  # noqa: E402
from gavel.prompt import MECHANISM_CLASSES  # noqa: E402
from gavel.qualify import records_from_receipts, resolve_slots  # noqa: E402
from gavel.receipts import verify_file  # noqa: E402

Z95 = 1.959963984540054
_SECTION = re.compile(r"### (ATK-\d+)\b(.*?)(?=\n### |\Z)", re.DOTALL)
_PREDICTION = re.compile(r"- (Primary|Fast|Informed) prediction: `attack=(true|false)`"
                         r"(?:, `mechanism_class=\"([^\"]*)\"`)?")


def parse_prereg(path: Path) -> dict:
    """{case_id: {arm: {"attack": bool, "mechanism_class": str or None}}}.
    mechanism_class is None when the prediction names no class."""
    text = Path(path).read_text(encoding="utf-8")
    predictions = {}
    for section in _SECTION.finditer(text):
        case_id, body = section.group(1), section.group(2)
        entry = {}
        for match in _PREDICTION.finditer(body):
            entry[match.group(1).lower()] = {"attack": match.group(2) == "true",
                                             "mechanism_class": match.group(3)}
        predictions[case_id] = entry
    return predictions


def normalize(verdict) -> dict | None:
    """A schema-v2 view of a v1 or v2 verdict; None when it is neither."""
    if not isinstance(verdict, dict):
        return None
    if "verdict" in verdict:
        value = verdict.get("verdict")
    elif isinstance(verdict.get("attack"), bool):
        value = "attack" if verdict["attack"] else "clean"
    else:
        return None
    return {"verdict": value,
            "mechanism_class": verdict.get("mechanism_class") or "",
            "offending_element": verdict.get("offending_element") or ""}


def wilson(k: int, n: int, z: float = Z95):
    """Wilson score interval for k successes in n trials; None when n is 0."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _rate(k: int, n: int) -> str:
    interval = wilson(k, n)
    if interval is None:
        return f"{k}/{n}"
    return f"{k}/{n} (Wilson 95% {interval[0]:.3f}-{interval[1]:.3f})"


def _cell(text) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def load_outcomes(receipts_path: Path) -> dict:
    """Verify the receipts and resolve them by the first-valid-attempt rule.

    Returns {"outcomes": {(case_id, arm): {"verdict": normalized or None,
    "unaudited": reason or None, "attempt": counted attempt or None}},
    "reattempted": [...], "unresolved": [...]}. Raises ValueError for an
    unverifiable file or a broken attempt protocol. Only run 1 is read.
    """
    receipts = verify_file(receipts_path, MECHANISM_CLASSES, content=True)
    records = records_from_receipts(receipts, legacy_attempts=True)
    slots = resolve_slots(records)
    if slots["errors"]:
        raise ValueError("attempt protocol broken: " + "; ".join(slots["errors"]))
    outcomes = {}
    for (cid, arm, run), record in slots["resolved"].items():
        if run != 1:
            continue
        normalized = normalize(record["verdict"])
        outcomes[(cid, arm)] = {"verdict": normalized, "attempt": record["attempt"],
                                "unaudited": None if normalized else "unreadable verdict"}
    for gap in slots["unresolved"]:
        cid, arm, run = gap["cell"]
        if run == 1:
            reasons = [r for r in gap["unaudited_reasons"] if r]
            outcomes[(cid, arm)] = {"verdict": None, "attempt": None,
                                    "unaudited": reasons[-1] if reasons else "UNAUDITED"}
    return {"outcomes": outcomes, "reattempted": slots["reattempted"],
            "unresolved": slots["unresolved"]}


def tally(predictions: dict, loaded: dict) -> dict:
    """Rows, gate decisions and hit counts, all computed."""
    outcomes = loaded["outcomes"]
    seen_arms = {arm for entry in predictions.values() for arm in entry}
    seen_arms |= {arm for _, arm in outcomes}
    arms = list(SCAN_REQUIRED_ARMS) + sorted(seen_arms - set(SCAN_REQUIRED_ARMS))
    cases = sorted(set(predictions) | {cid for cid, _ in outcomes})
    hits = {arm: {"attack": [0, 0], "class": [0, 0]} for arm in arms}
    rows, gates = [], []
    for cid in cases:
        for arm in arms:
            pred = predictions.get(cid, {}).get(arm)
            out = outcomes.get((cid, arm))
            judged = out["verdict"] if out else None
            attack_held = class_held = None
            if pred is not None:
                attack_held = judged is not None and (judged["verdict"] == "attack") == pred["attack"]
                hits[arm]["attack"][1] += 1
                hits[arm]["attack"][0] += attack_held
                if pred["mechanism_class"] is not None:
                    wanted = "attack" if pred["attack"] else "clean"
                    class_held = judged is not None and judged["verdict"] == wanted \
                        and judged["mechanism_class"] == pred["mechanism_class"]
                    hits[arm]["class"][1] += 1
                    hits[arm]["class"][0] += class_held
            if out is None:
                outcome = "no receipt"
            elif judged is None:
                outcome = f"UNAUDITED: {out['unaudited']}"
            else:
                outcome = judged["verdict"]
            rows.append({"case": cid, "arm": arm, "prediction": pred, "outcome": outcome,
                         "judged": judged, "attempt": out["attempt"] if out else None,
                         "attack_held": attack_held, "class_held": class_held})
        present = {arm: {"verdict": outcomes[(cid, arm)]["verdict"],
                         "unaudited": outcomes[(cid, arm)]["unaudited"]}
                   for arm in arms if (cid, arm) in outcomes}
        code, reasons = scan_exit_code(present)
        gates.append({"case": cid, "released": code == 0, "reasons": reasons})
    return {"arms": arms, "rows": rows, "gates": gates, "hits": hits,
            "reattempted": loaded["reattempted"]}


def _yes_no(value) -> str:
    return "n/a" if value is None else ("yes" if value else "no")


def _prediction_text(pred) -> str:
    if pred is None:
        return "n/a"
    text = "attack" if pred["attack"] else "clean"
    if pred["mechanism_class"]:
        text += f" ({pred['mechanism_class']})"
    return text


def render(result: dict) -> str:
    lines = ["| case | arm | predicted | outcome | mechanism_class | offending element | "
             "attack held | class held | counted attempt |",
             "|---|---|---|---|---|---|---|---|---|"]
    for row in result["rows"]:
        judged = row["judged"] or {}
        lines.append(f"| {row['case']} | {row['arm']} | {_prediction_text(row['prediction'])} | "
                     f"{_cell(row['outcome'])} | {_cell(judged.get('mechanism_class', ''))} | "
                     f"{_cell(judged.get('offending_element', ''))} | "
                     f"{_yes_no(row['attack_held'])} | {_yes_no(row['class_held'])} | "
                     f"{row['attempt'] if row['attempt'] is not None else '-'} |")
    lines += ["", "| case | gate released? | why |", "|---|---|---|"]
    for gate in result["gates"]:
        lines.append(f"| {gate['case']} | {'yes' if gate['released'] else 'no'} | "
                     f"{_cell('; '.join(gate['reasons']))} |")
    lines.append("")
    for arm in result["arms"]:
        k, n = result["hits"][arm]["attack"]
        lines.append(f"{arm} prediction hits, attack boolean only: {_rate(k, n)}")
        k, n = result["hits"][arm]["class"]
        lines.append(f"{arm} prediction hits, boolean and exact mechanism_class (offending "
                     f"element not checked): {_rate(k, n)}")
    unaudited = [f"{row['case']}/{row['arm']}" for row in result["rows"]
                 if row["outcome"].startswith("UNAUDITED")]
    absent = [f"{row['case']}/{row['arm']}" for row in result["rows"]
              if row["outcome"] == "no receipt"]
    reattempted = [f"{item['cell'][0]}/{item['cell'][1]} (attempt {item['counted_attempt']} "
                   f"of {item['attempts']} counted)" for item in result["reattempted"]]
    released = [gate["case"] for gate in result["gates"] if gate["released"]]
    lines.append(f"UNAUDITED outcomes: {', '.join(unaudited) or 'none'}")
    lines.append(f"no receipt: {', '.join(absent) or 'none'}")
    lines.append(f"re-attempted (first valid attempt counted): {', '.join(reattempted) or 'none'}")
    lines.append(f"gate released (every arm clean, primary and fast present): "
                 f"{', '.join(released) or 'none'}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Attack-round reconciliation table (v2).")
    ap.add_argument("--prereg", type=Path, required=True)
    ap.add_argument("--receipts", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if args.out is not None and args.out.exists():
        print(f"REFUSED: {args.out.name} exists; the table is written once", file=sys.stderr)
        return 2
    try:
        predictions = parse_prereg(args.prereg)
        table = render(tally(predictions, load_outcomes(args.receipts)))
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if args.out:
        args.out.write_text(table, encoding="utf-8", newline="\n")
        print(f"written: {args.out}")
    else:
        sys.stdout.write(table.encode("ascii", "backslashreplace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
