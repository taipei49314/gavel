"""gavel CLI: pin / scan / verify / exam / evaluate.

Exit codes

  scan  (SPEC §5: 「0＝clean（雙臂一致且無 findings）」, 1 findings,
        2 UNAUDITED; SPEC §6: arm divergence is itself a finding, and the
        informed arm is opt-in)
    0  clean: every required arm (primary and fast) ran and returned a valid
       clean verdict, so they agree, and every opt-in arm that ran did too
    1  findings: any attack, any inconclusive, or arms that disagree
    2  UNAUDITED: any arm without a valid verdict, or the scan could not be
       made (case file, receipts file, required arm not selected).
       UNAUDITED wins over findings; nothing UNAUDITED ever exits 0.
    An opt-in arm can only make the result stricter, never 0.

  exam, evaluate
    0  PASS
    1  FAIL (scored; a bar failed)
    2  INVALID_PAPER, INVALID_RECORDS, INCOMPLETE, or the paper, the output
       directory or the preflight was refused (never scored)
    3  COMPLETE: every cell resolved, scoring is external (e.g. a sealed
       paper); this is not a pass

  pin, verify: 0 done, 2 otherwise.

Any unexpected error exits 2, never 0 or 1. Replay (re-running a model to
reproduce a receipt) is not implemented; `verify` checks receipts offline.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

from .anchor import render_case
from .judge import VERDICT_VALUES, UnauditedError, check_approved, live_pin
from .prompt import MECHANISM_CLASSES
from .qualify import (ARMS, PaperError, evaluate, judge_case, load_paper,
                      records_from_receipts, run_paper)
from .receipts import ReceiptLog, build_receipt, verify_file

DEFAULT_BASE_URL_FALLBACK = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_S = 600.0

# Arms whose clean agreement scan requires for exit 0 (SPEC §5, §6). The
# informed (cloud) arm is opt-in and never required by default.
SCAN_REQUIRED_ARMS = ("primary", "fast")

EXAM_EXIT = {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2, "INVALID_RECORDS": 2,
             "INVALID_PAPER": 2, "COMPLETE": 3}

# ASCII only: help text must print on any console encoding.
EXIT_CODES_HELP = """\
exit codes:
  scan      0 clean: required arms primary and fast (and any opt-in arm)
              all returned valid clean verdicts
            1 findings: any attack, any inconclusive, or arms that disagree
            2 UNAUDITED: any arm without a valid verdict, or the scan could
              not be made; UNAUDITED wins, and never exits 0
  exam,     0 PASS, 1 FAIL, 2 INVALID_PAPER / INVALID_RECORDS / INCOMPLETE
  evaluate    or refused (never scored), 3 COMPLETE (scoring is external;
              not a pass)
  others    0 done, 2 otherwise; any unexpected error exits 2
replay (re-running a model to reproduce a receipt) is not implemented."""


def _ascii(text) -> str:
    """Text safe for any console encoding (model and daemon text may not be)."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def _err(message: str) -> None:
    print(_ascii(message), file=sys.stderr)


def _unique(items) -> list:
    return list(dict.fromkeys(items))


def _positive_seconds(text) -> float:
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a positive number of seconds")
    return value


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _expectations(args) -> tuple:
    """The expected chain head and receipt count: from --results (a paper's
    results.json) or from --expect-head / --expect-count."""
    head, count = args.expect_head, args.expect_count
    if args.results is None:
        return head, count
    if head is not None or count is not None:
        raise ValueError("give --results or --expect-head/--expect-count, not both")
    results_path = Path(args.results)
    data = json.loads(results_path.read_text(encoding="utf-8"))
    info = data.get("receipts") if isinstance(data, dict) else None
    if not isinstance(info, dict) or not isinstance(info.get("head"), str) \
            or not _is_count(info.get("count")):
        raise ValueError(f"{results_path.name} records no receipts.head and receipts.count")
    receipts_name = Path(args.receipts).name
    if info.get("file") not in (None, receipts_name):
        raise ValueError(f"{results_path.name} describes receipts file {info['file']!r}, "
                         f"not {receipts_name!r}")
    return info["head"], info["count"]


# --- pin ------------------------------------------------------------------------

def cmd_pin(args) -> int:
    code = 0
    for arm in _unique(args.arms):
        spec = ARMS[arm]
        try:
            pin = live_pin(spec["model"], args.base_url, spec["transport"])
            check_approved(pin, args.approved_models, transport=spec["transport"])
        except UnauditedError as exc:
            _err(f"{arm}: UNAUDITED ({exc.reason})")
            code = 2
            continue
        print(json.dumps({"arm": arm, **pin, "approved": True}, sort_keys=True))
    return code


# --- scan -----------------------------------------------------------------------

def scan_exit_code(outcomes: dict, required=SCAN_REQUIRED_ARMS) -> tuple[int, list[str]]:
    """The scan exit code (see the module docstring) and its reasons.

    outcomes maps every arm that ran, in run order, to its judge_case()
    result (anything with "verdict" and "unaudited"). required lists the
    arms that must have run.
    """
    reasons = []
    missing = [arm for arm in required if arm not in outcomes]
    if missing:
        reasons.append(f"required arm(s) not run: {', '.join(missing)}")
    values = {}
    for arm, res in outcomes.items():
        judged = res.get("verdict") if isinstance(res, dict) else None
        value = judged.get("verdict") if isinstance(judged, dict) else None
        if not isinstance(res, dict) or res.get("unaudited") or value not in VERDICT_VALUES:
            reasons.append(f"{arm}: UNAUDITED")
        else:
            values[arm] = value
    if reasons:
        return 2, reasons
    attacks = [arm for arm, value in values.items() if value == "attack"]
    inconclusive = [arm for arm, value in values.items() if value == "inconclusive"]
    if attacks:
        reasons.append(f"attack: {', '.join(attacks)}")
    if inconclusive:
        reasons.append(f"inconclusive: {', '.join(inconclusive)}")
    if len(set(values.values())) > 1:
        reasons.append("arms disagree: " + ", ".join(f"{arm}={value}"
                                                     for arm, value in values.items()))
    if reasons:
        return 1, reasons
    return 0, [f"clean, all arms agree: {', '.join(values)}"]


def cmd_scan(args) -> int:
    arms = _unique(args.arms)
    missing = [arm for arm in SCAN_REQUIRED_ARMS if arm not in arms]
    if missing:
        _err(f"UNAUDITED: scan needs the required arms {' and '.join(SCAN_REQUIRED_ARMS)} "
             f"(exit 0 means both local arms agree on clean); not selected: "
             f"{', '.join(missing)}")
        return 2
    case_path = Path(args.case)
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) \
                or not case["case_id"]:
            raise ValueError("no case_id")
        render_case(case)
    except (OSError, ValueError) as exc:
        _err(f"UNAUDITED: case file {case_path.name} cannot be used: "
             f"{type(exc).__name__}: {exc}")
        return 2
    receipts_path = Path(args.receipts)
    try:
        receipts_path.parent.mkdir(parents=True, exist_ok=True)
        log = ReceiptLog(receipts_path)  # refuses a v1/v2 or broken file before judging
    except (OSError, ValueError) as exc:
        _err(f"UNAUDITED: receipts file {receipts_path.name} cannot take v3 receipts: {exc}")
        return 2
    outcomes = {}
    for arm in arms:
        spec = ARMS[arm]
        # judge_case reads the live pin, checks approved-models (a missing or
        # unreadable file is UNAUDITED) and picks the transport's generate
        # function: Ollama for the local arms, agy for informed (CR-02, CR-14).
        res = judge_case(case, spec["model"], args.base_url, args.timeout,
                         approved_models=args.approved_models,
                         transport_name=spec["transport"])
        log.append(build_receipt(case_id=case["case_id"], arm=arm, run=1, attempt=1,
                                 judgment=res))
        outcomes[arm] = res
        if res["unaudited"]:
            print(_ascii(f"{arm}: UNAUDITED: {res['unaudited']}"))
        else:
            print(f"{arm}: {json.dumps(res['verdict'], sort_keys=True)}")
    code, reasons = scan_exit_code(outcomes)
    print(_ascii(f"exit {code}: {'; '.join(reasons)}"))
    return code


# --- verify ---------------------------------------------------------------------

def cmd_verify(args) -> int:
    try:
        head, count = _expectations(args)
        receipts = verify_file(args.receipts, MECHANISM_CLASSES, content=args.content,
                               expect_head=head, expect_count=count)
    except (OSError, ValueError) as exc:
        _err(f"FAIL: {exc}")
        return 2
    mode = "content+structural" if args.content else "structural"
    tail = "; tail checked against the expected head/count" \
        if head is not None or count is not None else ""
    print(f"OK: {len(receipts)} receipts valid ({mode}{tail})")
    return 0


# --- exam and evaluate ------------------------------------------------------------

def _print_report(report: dict) -> None:
    print(_ascii(f"status: {report['status']} (paper {report['paper_id']})"))
    for bar in report["bars"]:
        print(_ascii(f"  [{'ok' if bar['ok'] else 'NO'}] {bar['bar']}: {bar['detail']}"))
    for error in report["errors"]:
        print(_ascii(f"  error: {error}"))
    for cell in report["gaps"]["missing"]:
        print(_ascii(f"  no record: {'/'.join(map(str, cell))}"))
    for gap in report["gaps"]["unresolved"]:
        print(_ascii(f"  no valid attempt: {'/'.join(map(str, gap['cell']))} "
                     f"({gap['attempts']} attempt(s), cap {gap['cap']}): "
                     f"{gap['unaudited_reasons']}"))
    for item in report["reattempted"]:
        print(_ascii(f"  re-attempted: {'/'.join(map(str, item['cell']))} "
                     f"({item['attempts']} attempts, counted attempt "
                     f"{item['counted_attempt']})"))
    if report.get("note"):
        print(_ascii(f"  note: {report['note']}"))


def cmd_exam(args) -> int:
    try:
        result = run_paper(args.manifest, args.out, base_url=args.base_url,
                           timeout_s=args.timeout, approved_path=args.approved_models)
    except PaperError as exc:
        _err(f"REFUSED: {exc}")
        return 2
    except UnauditedError as exc:
        _err(f"UNAUDITED: preflight refused the paper before any judgment: {exc.reason}")
        return 2
    report = result["report"]
    _print_report(report)
    receipts = result["results"]["receipts"]
    print(_ascii(f"written to {args.out}: receipts.jsonl ({receipts['count']} receipts, "
                 f"head {receipts['head']}), results.json, report.json"))
    return EXAM_EXIT[report["status"]]


def cmd_evaluate(args) -> int:
    try:
        paper = load_paper(args.manifest)
        head, count = _expectations(args)
        receipts = verify_file(args.receipts, MECHANISM_CLASSES, content=True,
                               expect_head=head, expect_count=count)
        records = records_from_receipts(receipts, legacy_attempts=args.legacy_attempts)
    except PaperError as exc:
        _err(f"REFUSED: {exc}")
        return 2
    except (OSError, ValueError) as exc:
        _err(f"FAIL: {exc}")
        return 2
    report = evaluate(paper["manifest"], records)
    print(json.dumps(report, sort_keys=True, indent=2))
    return EXAM_EXIT[report["status"]]


def cmd_qualify(args) -> int:
    # The directory-driven exam derived its expected matrix from the arms and
    # cases of the same run (CR-03/CR-10) and was removed.
    _err("UNAUDITED: `qualify` is retired; run a locked paper with "
         "`gavel exam --manifest <paper.json> --out <dir>`")
    return 2


# --- parser -------------------------------------------------------------------------

def build_parser(default_timeout: float = DEFAULT_TIMEOUT_S) -> argparse.ArgumentParser:
    base_url = os.environ.get("GAVEL_OLLAMA") or DEFAULT_BASE_URL_FALLBACK
    approved = os.environ.get("GAVEL_APPROVED_MODELS") or None  # None: repo-root file
    raw = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(prog="gavel", description="Pinned local-LLM judge "
                                     "for the wash family.", epilog=EXIT_CODES_HELP,
                                     formatter_class=raw)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def connection(p, timeout=True):
        p.add_argument("--base-url", default=base_url, help="Ollama daemon URL")
        if timeout:
            p.add_argument("--timeout", type=_positive_seconds, default=default_timeout,
                           help="seconds per judgment")
        p.add_argument("--approved-models", default=approved,
                       help="approved-models.json (default: the file at the repo root)")

    def tail_checks(p):
        p.add_argument("--results", help="a paper's results.json: check the receipts "
                                         "count and chain head it records")
        p.add_argument("--expect-head", help="expected receipt_id of the last receipt")
        p.add_argument("--expect-count", type=int, help="expected number of receipts")

    p = sub.add_parser("pin", help="print model pin facts and approval state",
                       description="Read each arm's live pin and check it against "
                                   "approved-models.json. The informed arm is opt-in.")
    p.add_argument("--arms", nargs="+", default=list(SCAN_REQUIRED_ARMS), choices=list(ARMS))
    connection(p, timeout=False)
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("scan", help="judge one case file (exit 0 clean, 1 findings, "
                                    "2 UNAUDITED)",
                       description="Judge one case with the required arms primary and "
                                   "fast (and any opt-in arm).",
                       epilog=EXIT_CODES_HELP, formatter_class=raw)
    p.add_argument("case")
    p.add_argument("--arms", nargs="+", default=list(SCAN_REQUIRED_ARMS), choices=list(ARMS),
                   help="arms to run; primary and fast are required, informed is opt-in")
    p.add_argument("--receipts", default="receipts/scan.jsonl",
                   help="v3 receipts file to append to (a v1/v2 file is refused)")
    connection(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("verify", help="verify a receipts file offline (replay is not "
                                      "implemented)",
                       description="Structural verification (hash chain, receipt ids, "
                                   "pins), optionally content verification and a tail "
                                   "check. Replay, i.e. re-running the model to reproduce "
                                   "a verdict, is not implemented.")
    p.add_argument("receipts")
    p.add_argument("--content", action="store_true",
                   help="also re-hash the embedded texts and re-parse the raw output "
                        "(v2 and v3 receipts); this never calls a model")
    tail_checks(p)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("exam", help="run a locked paper once (exit 0 PASS, 1 FAIL, "
                                    "2 not scored, 3 COMPLETE)",
                       description="Run a locked paper manifest once with "
                                   "gavel.qualify.run_paper and write receipts.jsonl, "
                                   "results.json and report.json into --out.",
                       epilog=EXIT_CODES_HELP, formatter_class=raw)
    p.add_argument("--manifest", required=True, help="the locked paper manifest (JSON)")
    p.add_argument("--out", required=True, help="output directory (must not hold a run)")
    connection(p)
    p.set_defaults(func=cmd_exam)

    p = sub.add_parser("evaluate", help="re-evaluate a paper from its receipts",
                       description="Verify the receipts (content and, with --results, "
                                   "the tail), rebuild the records and evaluate them "
                                   "against the locked manifest. Prints the report JSON.",
                       epilog=EXIT_CODES_HELP, formatter_class=raw)
    p.add_argument("--manifest", required=True)
    p.add_argument("--receipts", required=True)
    p.add_argument("--legacy-attempts", action="store_true",
                   help="number the attempts of v1/v2 receipts by file order")
    tail_checks(p)
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("qualify", help="retired; use exam")
    p.set_defaults(func=cmd_qualify)
    return parser


def main(argv=None) -> int:
    env_timeout = os.environ.get("GAVEL_TIMEOUT")
    try:
        default_timeout = _positive_seconds(env_timeout) if env_timeout else DEFAULT_TIMEOUT_S
    except (ValueError, argparse.ArgumentTypeError):
        _err("UNAUDITED: GAVEL_TIMEOUT must be a positive number of seconds")
        return 2
    args = build_parser(default_timeout).parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # fail closed: an unexpected error is never 0 or 1
        _err(f"UNAUDITED: unexpected error: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
