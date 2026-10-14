"""Generate the attack-round reconciliation table from locked sources.

Reads the evaluator's PREREG (predictions) and the receipts file (outcomes)
and emits the reconciliation table. This exists because hand-written
reconciliation drifts: the round-1 report quoted a chat summary instead of
the locked PREREG and mis-stated ATK-005 (see REPORT ERRATUM). Predictions,
outcomes and hit-rates must come from bytes, not prose.

Usage:
  python tools/tally_attack.py --prereg <PREREG-codex.md> \
      --receipts <receipts.jsonl> [--out <table.md>]
"""

import argparse
import json
import re
from pathlib import Path


def parse_prereg(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    predictions = {}
    for section in re.finditer(r"### (ATK-\d+)\b(.*?)(?=\n### |\Z)", text, re.DOTALL):
        case_id, body = section.group(1), section.group(2)
        entry = {}
        for arm in ("primary", "fast"):
            m = re.search(rf"- {arm.capitalize()} prediction: `attack=(true|false)`", body)
            if m:
                entry[arm] = m.group(1) == "true"
        predictions[case_id] = entry
    return predictions


def parse_receipts(path: Path) -> dict:
    outcomes = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        v = r.get("verdict")
        key = (r["case_id"], r["arm"])
        outcomes[key] = (v.get("attack") if isinstance(v, dict) else None,
                         r.get("unaudited_reason"))
    return outcomes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prereg", type=Path, required=True)
    ap.add_argument("--receipts", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    predictions = parse_prereg(args.prereg)
    outcomes = parse_receipts(args.receipts)
    cases = sorted(set(predictions) | {k[0] for k in outcomes})

    lines = [
        "| case | pred 35b | act 35b | 35b held | pred 9b | act 9b | 9b held | gate released? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    hits = {"primary": [0, 0], "fast": [0, 0]}
    for cid in cases:
        pred = predictions.get(cid, {})
        cells, flagged = [], False
        for arm in ("primary", "fast"):
            actual, unaudited = outcomes.get((cid, arm), (None, "no receipt"))
            actual_s = "UNAUD" if unaudited else str(actual)
            p, a = pred.get(arm), actual
            held = (p is not None and a is not None and p == a)
            if held:
                hits[arm][0] += 1
            if p is not None:
                hits[arm][1] += 1
            cells += [str(p).lower() if p is not None else "n/a",
                      actual_s, "✓" if held else "✗"]
            flagged = flagged or (a is True)
        lines.append(f"| {cid} | " + " | ".join(cells) +
                     f" | {'yes' if not flagged else 'no'} |")

    summary = [
        "",
        f"primary prediction hits: {hits['primary'][0]}/{hits['primary'][1]}",
        f"fast prediction hits: {hits['fast'][0]}/{hits['fast'][1]}",
        "gate released (no arm flagged): " +
        ", ".join(cid for cid in cases
                  if not any(outcomes.get((cid, arm), (None,))[0] is True
                             for arm in ("primary", "fast"))) or "none",
    ]
    table = "\n".join(lines + summary) + "\n"
    if args.out:
        args.out.write_text(table, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
