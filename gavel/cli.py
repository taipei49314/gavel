"""gavel CLI: pin / scan / verify / qualify.

Exit codes (SPEC §5): 0 clean, 1 findings, 2 UNAUDITED.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .anchor import render_case, sha256_text
from .judge import UnauditedError, extract_json, generate, get_pin, validate_verdict
from .prompt import MECHANISM_CLASSES, render_prompt
from .qualify import ARMS, evaluate, run_exam
from .receipts import make_receipt, verify_file, write_receipt

DEFAULT_BASE_URL = os.environ.get("GAVEL_OLLAMA", "http://127.0.0.1:11434")
DEFAULT_TIMEOUT = float(os.environ.get("GAVEL_TIMEOUT", "600"))


def cmd_pin(args) -> int:
    for arm in args.arms:
        model = ARMS[arm]
        try:
            pin = get_pin(model, args.base_url)
        except UnauditedError as exc:
            print(f"{arm}: UNAUDITED ({exc.reason})", file=sys.stderr)
            return 2
        print(json.dumps({"arm": arm, **pin}, sort_keys=True))
    return 0


def cmd_scan(args) -> int:
    receipts_path = Path(args.receipts)
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    anchor_block = render_case(case)
    prompt = render_prompt(anchor_block)
    pins, outcomes = {}, []
    exit_code = 0
    for arm in args.arms:
        model = ARMS[arm]
        pin = get_pin(model, args.base_url)
        pins[arm] = pin
        try:
            raw = generate(model, prompt, args.base_url, args.timeout)
            verdict, unaudited = validate_verdict(
                extract_json(raw), MECHANISM_CLASSES), None
        except UnauditedError as exc:
            raw, verdict, unaudited = None, None, exc.reason
        receipt = make_receipt(case["case_id"], arm, pin, sha256_text(prompt),
                               sha256_text(anchor_block), raw, verdict, unaudited)
        write_receipt(receipts_path, receipt)
        outcomes.append((arm, verdict, unaudited))
    for arm, verdict, unaudited in outcomes:
        if unaudited:
            print(f"{arm}: UNAUDITED — {unaudited}")
            exit_code = 2
        else:
            print(f"{arm}: {json.dumps(verdict, sort_keys=True)}")
            if verdict["attack"] and exit_code == 0:
                exit_code = 1
    return exit_code


def cmd_verify(args) -> int:
    try:
        receipts = verify_file(args.receipts)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    print(f"OK: {len(receipts)} receipts structurally valid")
    return 0


def cmd_qualify(args) -> int:
    cases_dir = Path(args.cases)
    meta = {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(cases_dir.glob("*.json"))}
    records = run_exam(cases_dir, Path(args.out), base_url=args.base_url,
                       timeout_s=args.timeout, repeat_s=args.repeat_s,
                       arms=tuple(args.arms))
    report = evaluate(meta, records)
    (Path(args.out) / "report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2))
    for b in report["bars"]:
        print(("PASS" if b["ok"] else "FAIL"), b["bar"], "—", b["detail"])
    print("fast-arm divergence:", report["fast_arm_divergence"])
    print("OVERALL:", "PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gavel")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pin", help="print model pin facts")
    p.add_argument("--arms", nargs="+", default=["primary", "fast"],
                   choices=list(ARMS))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("scan", help="judge one case file")
    p.add_argument("case")
    p.add_argument("--arms", nargs="+", default=["primary", "fast"],
                   choices=list(ARMS))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.add_argument("--receipts", default="receipts/scan.jsonl")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("verify", help="structurally verify a receipts file")
    p.add_argument("receipts")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("qualify", help="run the PREREG exam")
    p.add_argument("--cases", default="cases")
    p.add_argument("--out", default="results/round-0")
    p.add_argument("--arms", nargs="+", default=["primary", "fast"],
                   choices=list(ARMS))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.add_argument("--repeat-s", type=int, default=3)
    p.set_defaults(func=cmd_qualify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
