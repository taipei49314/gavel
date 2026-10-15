"""gavel CLI: pin / scan / verify / qualify.

Exit codes (SPEC §5): 0 clean, 1 findings, 2 UNAUDITED.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .judge import UnauditedError, check_approved, get_pin
from .prompt import MECHANISM_CLASSES
from .qualify import ARMS, judge_case
from .receipts import append_receipt, build_receipt, verify_file

DEFAULT_BASE_URL = os.environ.get("GAVEL_OLLAMA", "http://127.0.0.1:11434")
DEFAULT_TIMEOUT = float(os.environ.get("GAVEL_TIMEOUT", "600"))
# None means gavel.judge.default_approved_path(): the repo-root file, never
# the working directory (CR-02).
DEFAULT_APPROVED = os.environ.get("GAVEL_APPROVED_MODELS") or None


def _pin_for(arm: str, base_url: str) -> dict:
    spec = ARMS[arm]
    if spec.get("transport", "ollama") == "ollama":
        return get_pin(spec["model"], base_url)
    return {"model": spec["model"], "manifest_digest": None,
            "note": "cloud arm, digest n/a"}


def cmd_pin(args) -> int:
    code = 0
    for arm in args.arms:
        try:
            pin = _pin_for(arm, args.base_url)
            check_approved(pin, args.approved_models,
                           transport=ARMS[arm].get("transport", "ollama"))
            print(json.dumps({"arm": arm, **pin, "approved": True}, sort_keys=True))
        except UnauditedError as exc:
            print(f"{arm}: UNAUDITED ({exc.reason})", file=sys.stderr)
            code = 2
    return code


def cmd_scan(args) -> int:
    receipts_path = Path(args.receipts)
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    outcomes = []
    exit_code = 0
    for arm in args.arms:
        spec = ARMS[arm]
        # judge_case reads the live pin and checks approved-models itself
        # (one judgment path for exam and scan, CR-02); the pin it read is
        # recorded even when it is not approved (CR-14).
        res = judge_case(case, spec["model"], args.base_url, args.timeout,
                         approved_models=args.approved_models,
                         transport_name=spec.get("transport", "ollama"))
        append_receipt(receipts_path, build_receipt(
            case_id=case["case_id"], arm=arm, run=1, attempt=1, judgment=res))
        outcomes.append((arm, res))
    for arm, res in outcomes:
        if res["unaudited"]:
            print(f"{arm}: UNAUDITED — {res['unaudited']}")
            exit_code = 2
        else:
            v = res["verdict"]
            print(f"{arm}: {json.dumps(v, sort_keys=True)}")
            if v["verdict"] == "attack" and exit_code == 0:
                exit_code = 1
    return exit_code


def cmd_verify(args) -> int:
    try:
        receipts = verify_file(args.receipts, MECHANISM_CLASSES, content=args.content)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    mode = "content+structural" if args.content else "structural"
    print(f"OK: {len(receipts)} receipts valid ({mode})")
    return 0


def cmd_qualify(args) -> int:
    # The directory-driven exam (run_exam) derived its expected matrix from
    # the arms and cases of the same run (CR-03/CR-10) and was removed. A
    # paper is now run from a locked manifest by gavel.qualify.run_paper();
    # its CLI command is not wired yet, so this fails closed.
    print("UNAUDITED: `qualify` without a locked paper manifest is retired; "
          "use gavel.qualify.run_paper (CLI command pending)", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gavel")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pin", help="print model pin facts and approval state")
    p.add_argument("--arms", nargs="+", default=["primary", "fast", "informed"],
                   choices=list(ARMS))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--approved-models", default=DEFAULT_APPROVED)
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("scan", help="judge one case file")
    p.add_argument("case")
    p.add_argument("--arms", nargs="+", default=["primary", "fast"],
                   choices=list(ARMS))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.add_argument("--receipts", default="receipts/scan.jsonl")
    p.add_argument("--approved-models", default=DEFAULT_APPROVED)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("verify", help="verify a receipts file")
    p.add_argument("receipts")
    p.add_argument("--content", action="store_true",
                   help="re-hash embedded content and re-parse raw responses "
                        "(v2 receipts); replaying the model is a separate feature")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("qualify", help="run the PREREG exam")
    p.add_argument("--cases", default="cases")
    p.add_argument("--out", default="results/round-2")
    p.add_argument("--arms", nargs="+", default=["primary", "fast", "informed"],
                   choices=list(ARMS))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.set_defaults(func=cmd_qualify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
