"""Locked-paper exam harness: paper manifests, the exam driver, bar evaluation.

Exam-validity contract (takeover audit 2026-10-15: CR-01, CR-03, CR-10):

- A paper is defined only by a locked manifest (see validate_manifest for
  the format): paper id, the case list with each case file's sha256, tier
  and role, the arms, the gating arm, runs per arm and tier, the attempt
  cap, the scoring mode and the bars (tier and role counts, a_min, ...).
  evaluate() derives the expected (case, arm, run) matrix from the manifest
  alone; never from the records, a cases directory or the arms that happened
  to run.
- Attempts (CR-01): every judgment record carries an integer attempt number.
  Within a (case, arm, run) slot the first VALID attempt counts. Attempts
  must be numbered 1..n with no gap (every attempt receipted), n must not
  exceed the manifest's attempt cap, and no attempt may follow a valid one.
  Duplicate (case, arm, run, attempt) records are an error. There is no
  last-record-wins. Every slot that needed more than one attempt is
  disclosed in the report.
- run_paper() is the committed exam driver. It re-attempts an UNAUDITED slot
  immediately, up to the cap, and receipts every attempt. It refuses to
  write into a directory that already holds a paper run, so a paper is run
  once; there are no operator re-runs. evaluate() over the receipts it wrote
  (records_from_receipts) reproduces its report.
- Status precedence: INVALID_PAPER (the manifest is unusable, including any
  enabled bar with a zero denominator) > INVALID_RECORDS (the attempt
  protocol is broken) > INCOMPLETE (a cell has no record, or no valid attempt
  within the cap; this covers arm subsets and missing cases) > COMPLETE
  (scoring "external", e.g. a sealed paper scored after reveal) | PASS |
  FAIL. Only PASS passes.
- Verdict schema v2: {"verdict": "attack|clean|inconclusive", ...}.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath

from . import __version__
from .anchor import ANCHOR_VERSION, render_case, sha256_text
from .judge import (CLOUD_TRANSPORTS, OLLAMA, OPTION_KEYS, SCHEMA_VERSION,
                    TRANSPORT_ERRORS, UnauditedError, agy_generate,
                    check_approved, extract_json, generate, get_pin,
                    get_runtime_version, live_pin, resolve_options,
                    validate_verdict)
from .prompt import MECHANISM_CLASSES, PROMPT_VERSION, render_prompt
from .receipts import RECEIPT_VERSION, ReceiptLog, build_receipt

DEFAULT_BASE_URL = "http://127.0.0.1:11434"

# Default arm specs for ad-hoc scans. Exams take their arms from the manifest.
ARMS = {
    "primary": {"model": "qwen3.5:35b-a3b", "role": "gating", "transport": "ollama"},
    "fast": {"model": "qwen3.5:9b", "role": "recorded", "transport": "ollama"},
    "informed": {"model": "gemini-4-argon-high", "role": "recorded", "transport": "agy"},
}

MANIFEST_VERSION = 1
TIERS = ("S", "A", "B")
ROLES = ("exam", "negative", "agree")
SCORING_MODES = ("bars", "external")
MAX_ATTEMPT_CAP = 10
PAPER_OUTPUTS = ("receipts.jsonl", "results.json", "report.json")

_MANIFEST_REQUIRED = ("manifest_version", "paper_id", "cases", "arms", "gating_arm",
                      "attempt_cap", "scoring")
_MANIFEST_OPTIONAL = ("bars", "options", "runtime", "note")
_CASE_KEYS = frozenset({"case_id", "path", "sha256", "tier", "role"})
_ARM_REQUIRED = ("model", "transport", "runs")
_ARM_OPTIONAL = ("role", "note")
_BAR_KEYS = ("tier_counts", "role_counts", "s_all", "a_min", "negative",
             "agree_min_rate", "s_reproducibility")
_NEGATIVE_KEYS = frozenset({"hard_max", "soft_max", "inconclusive_max",
                            "soft_confidence_below"})
_CONTROL_ROLES = ("negative", "agree")
_RUNTIME_KEYS = ("ollama_version",)


class PaperError(ValueError):
    """The paper (manifest or case files) cannot be used; nothing was judged."""


# --- the single judgment path --------------------------------------------------

def _generator_for(transport_name: str, generate_fn=None):
    if generate_fn is not None:
        return generate_fn
    if transport_name == OLLAMA:
        return generate
    if transport_name == "agy":
        return agy_generate
    return None


def _mark_unaudited(result: dict, reason: str, exc: UnauditedError | None = None) -> None:
    result["verdict"] = None
    result["unaudited"] = reason
    if exc is not None:
        if result["raw"] is None and exc.raw is not None:
            result["raw"] = exc.raw  # CR-07: keep whatever the model returned
        if exc.generation:
            result["generation"] = dict(exc.generation)


def judge_case(case: dict, model: str, base_url: str, timeout_s: float,
               transport=None, approved_models=None, generate_fn=None, *,
               transport_name: str = OLLAMA, options: dict | None = None,
               pinned_runtime: dict | None = None) -> dict:
    """One judgment: the single judgment path for exam and scan.

    Never raises for a judgment failure. Returns a dict with "verdict"
    (schema-v2 dict, or None) and "unaudited" (reason, or None), plus every
    fact a receipt records: raw output (kept on UNAUDITED, CR-07), prompt and
    anchor texts, hashes and versions, transport name and version, the pin
    read before and after the call, options and generation facts, and
    execution settings.

    Order (CR-02/F4): live pin -> approved-models check (approved_models
    None means the repo-root approved-models.json) -> Ollama version (and the
    manifest's pinned version, if any) -> generate -> for Ollama, the digest
    and version are read again and must be unchanged -> strict parse ->
    schema validation. transport is the HTTP callable for Ollama (tests
    inject a fake); transport_name selects the transport ("ollama" or a
    cloud transport such as "agy").
    """
    anchor_block = render_case(case)
    prompt = render_prompt(anchor_block)
    is_local = transport_name == OLLAMA
    result = {
        "verdict": None,
        "unaudited": None,
        "raw": None,
        "anchor_text": anchor_block,
        "prompt_text": prompt,
        "anchor_sha256": sha256_text(anchor_block),
        "prompt_sha256": sha256_text(prompt),
        "prompt_version": PROMPT_VERSION,
        "anchor_version": ANCHOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "transport": {"name": transport_name, "version": None},
        "pin": {"model": model, "manifest_digest": None},
        "pin_after": None,
        "options": {},
        "generation": {},
        "execution": ({"base_url": base_url, "timeout_s": timeout_s} if is_local
                      else {"timeout_s": timeout_s}),
    }
    try:
        gen = _generator_for(transport_name, generate_fn)
        if gen is None:
            raise UnauditedError(f"unknown transport: {transport_name!r}")
        pin = live_pin(model, base_url, transport_name, transport=transport)
        result["pin"] = pin
        check_approved(pin, approved_models, transport=transport_name)
        version = None
        if is_local:
            result["options"] = resolve_options(options)
            version = get_runtime_version(base_url, transport=transport)
            result["transport"]["version"] = version
            pinned = (pinned_runtime or {}).get("ollama_version")
            if pinned is not None and version != pinned:
                raise UnauditedError(f"ollama version {version} is not the pinned {pinned}")
        out = gen(model, prompt, base_url, timeout_s, transport=transport,
                  options=result["options"] if is_local else None)
        if not isinstance(out, dict) or not isinstance(out.get("raw"), str):
            raise UnauditedError("transport returned no text")
        result["raw"] = out["raw"]
        result["generation"] = dict(out.get("generation") or {})
        if out.get("transport_version") is not None:
            result["transport"]["version"] = out["transport_version"]
        if is_local:
            after = get_pin(model, base_url, transport=transport)
            result["pin_after"] = after
            if after.get("manifest_digest") != pin.get("manifest_digest"):
                raise UnauditedError(
                    f"model digest changed during judgment: {pin.get('manifest_digest')} "
                    f"-> {after.get('manifest_digest')}")
            version_after = get_runtime_version(base_url, transport=transport)
            if version_after != version:
                raise UnauditedError(
                    f"ollama version changed during judgment: {version} -> {version_after}")
        result["verdict"] = validate_verdict(extract_json(result["raw"]), MECHANISM_CLASSES)
    except UnauditedError as exc:
        _mark_unaudited(result, exc.reason, exc)
    except TRANSPORT_ERRORS as exc:  # CR-14 safety net for a transport not covered above
        _mark_unaudited(result, f"transport error: {type(exc).__name__}: {exc}")
    return result


# --- paper manifest -----------------------------------------------------------

def _is_int(value, minimum=None) -> bool:
    ok = isinstance(value, int) and not isinstance(value, bool)
    return ok and (minimum is None or value >= minimum)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_sha256(value) -> bool:
    return isinstance(value, str) and len(value) == 64 \
        and all(c in "0123456789abcdef" for c in value)


def _is_safe_relpath(value) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def runs_for(arm_spec: dict, tier) -> int:
    """Runs of one arm on a case of the given tier ("default" otherwise)."""
    runs = arm_spec["runs"]
    if tier is not None and tier in runs:
        return runs[tier]
    return runs["default"]


def census(manifest: dict) -> dict:
    """Exam cases per tier and cases per role, counted from the case list."""
    tiers = {t: 0 for t in TIERS}
    roles = {r: 0 for r in ROLES}
    for case in manifest["cases"]:
        roles[case["role"]] += 1
        if case["role"] == "exam" and case["tier"] in tiers:
            tiers[case["tier"]] += 1
    return {"tiers": tiers, "roles": roles}


def validate_manifest(manifest) -> list[str]:
    """Every reason the manifest cannot define a paper; empty when it can.

    Format (JSON object; manifest_version 1):
      paper_id     non-empty string
      cases        non-empty list of {"case_id", "path", "sha256", "tier",
                   "role"}: path is relative to the manifest file, forward
                   slashes, no ".."; sha256 is of the case file's bytes;
                   tier is "S" | "A" | "B" | null; role is "exam" |
                   "negative" | "agree"
      arms         {name: {"model", "transport": "ollama" | cloud transport,
                   "runs": {"default": n, "S"/"A"/"B": n}}} (optional
                   "role", "note")
      gating_arm   one of arms, on transport "ollama" (cloud verdicts are
                   recorded only, SPEC §6)
      attempt_cap  integer 1..MAX_ATTEMPT_CAP
      scoring      "bars" (scored here) or "external" (completeness only,
                   e.g. a sealed paper scored after reveal; never PASS)
      bars         with scoring "bars": tier_counts {"S","A","B": n} and
                   role_counts {"negative", "agree": n} (both must equal the
                   case list), and at least one of: s_all (bool), a_min
                   (int), negative {"hard_max", "soft_max",
                   "inconclusive_max", "soft_confidence_below"},
                   agree_min_rate (0..1], s_reproducibility (bool). An
                   enabled bar whose denominator is zero makes the paper
                   invalid.
      options      optional generation options (temperature, num_ctx, seed)
      runtime      optional {"ollama_version": "x.y.z"} pinned runtime
      note         optional free text
    """
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    problems = [f"missing key {key!r}" for key in _MANIFEST_REQUIRED if key not in manifest]
    unknown = set(manifest) - set(_MANIFEST_REQUIRED) - set(_MANIFEST_OPTIONAL)
    if unknown:
        problems.append(f"unknown keys {sorted(unknown)}")
    if problems:
        return problems

    if not _is_int(manifest["manifest_version"]) or manifest["manifest_version"] != MANIFEST_VERSION:
        problems.append(f"manifest_version must be {MANIFEST_VERSION}")
    if not isinstance(manifest["paper_id"], str) or not manifest["paper_id"].strip():
        problems.append("paper_id must be a non-empty string")

    cases = manifest["cases"]
    if not isinstance(cases, list) or not cases:
        problems.append("cases must be a non-empty list")
        cases = []
    seen = set()
    for i, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != _CASE_KEYS:
            problems.append(f"cases[{i}]: keys must be exactly {sorted(_CASE_KEYS)}")
            continue
        cid = case["case_id"]
        if not isinstance(cid, str) or not cid:
            problems.append(f"cases[{i}]: case_id must be a non-empty string")
            continue
        if cid in seen:
            problems.append(f"{cid}: duplicate case_id")
        seen.add(cid)
        if not _is_safe_relpath(case["path"]):
            problems.append(f"{cid}: path must be relative, forward-slash, without '..'")
        if not _is_sha256(case["sha256"]):
            problems.append(f"{cid}: sha256 must be 64 lowercase hex digits")
        if case["role"] not in ROLES:
            problems.append(f"{cid}: role must be one of {ROLES}")
        if case["tier"] is not None and case["tier"] not in TIERS:
            problems.append(f"{cid}: tier must be one of {TIERS} or null")

    arms = manifest["arms"]
    if not isinstance(arms, dict) or not arms:
        problems.append("arms must be a non-empty object")
        arms = {}
    for name, spec in arms.items():
        if not isinstance(spec, dict):
            problems.append(f"arm {name}: spec must be an object")
            continue
        missing = [k for k in _ARM_REQUIRED if k not in spec]
        extra = set(spec) - set(_ARM_REQUIRED) - set(_ARM_OPTIONAL)
        if missing or extra:
            problems.append(f"arm {name}: missing {missing}, unknown {sorted(extra)}")
            continue
        if not isinstance(spec["model"], str) or not spec["model"]:
            problems.append(f"arm {name}: model must be a non-empty string")
        if spec["transport"] != OLLAMA and spec["transport"] not in CLOUD_TRANSPORTS:
            problems.append(f"arm {name}: unknown transport {spec['transport']!r}")
        runs = spec["runs"]
        if not isinstance(runs, dict) or "default" not in runs:
            problems.append(f"arm {name}: runs must be an object with a 'default' entry")
            continue
        for key, value in runs.items():
            if key != "default" and key not in TIERS:
                problems.append(f"arm {name}: runs key {key!r} is not a tier")
            if not _is_int(value, 1):
                problems.append(f"arm {name}: runs[{key!r}] must be an integer >= 1")

    gating = manifest["gating_arm"]
    if not isinstance(gating, str) or gating not in arms:
        problems.append(f"gating_arm {gating!r} is not one of the arms")
    elif isinstance(arms[gating], dict) and arms[gating].get("transport") != OLLAMA:
        problems.append("gating arm must use the local pinned transport 'ollama' "
                        "(cloud verdicts are recorded only)")

    cap = manifest["attempt_cap"]
    if not _is_int(cap, 1) or cap > MAX_ATTEMPT_CAP:
        problems.append(f"attempt_cap must be an integer from 1 to {MAX_ATTEMPT_CAP}")

    options = manifest.get("options")
    if options is not None:
        if not isinstance(options, dict) or set(options) - set(OPTION_KEYS):
            problems.append(f"options may only hold {list(OPTION_KEYS)}")
        else:
            if "temperature" in options and not _is_number(options["temperature"]):
                problems.append("options.temperature must be a number")
            if "num_ctx" in options and not _is_int(options["num_ctx"], 1):
                problems.append("options.num_ctx must be a positive integer")
            if "seed" in options and not _is_int(options["seed"]):
                problems.append("options.seed must be an integer")

    runtime = manifest.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict) or set(runtime) - set(_RUNTIME_KEYS) \
                or not all(isinstance(v, str) and v for v in runtime.values()):
            problems.append(f"runtime may only hold non-empty strings for {list(_RUNTIME_KEYS)}")

    scoring = manifest["scoring"]
    if scoring not in SCORING_MODES:
        problems.append(f"scoring must be one of {SCORING_MODES}")
    elif scoring == "external":
        if manifest.get("bars") is not None:
            problems.append("scoring 'external' takes no bars")
    elif not problems:  # bar checks need a sound case list and arms
        problems.extend(_validate_bars(manifest))
    return problems


def _validate_bars(manifest: dict) -> list[str]:
    bars = manifest.get("bars")
    if not isinstance(bars, dict):
        return ["scoring 'bars' requires a bars object"]
    problems = []
    unknown = set(bars) - set(_BAR_KEYS)
    if unknown:
        problems.append(f"unknown bar keys {sorted(unknown)}")
    counts = census(manifest)
    tiers, roles = counts["tiers"], counts["roles"]

    declared = bars.get("tier_counts")
    if not isinstance(declared, dict) or set(declared) - set(TIERS) \
            or not all(_is_int(v, 0) for v in declared.values()):
        problems.append("bars.tier_counts must map S/A/B to non-negative integers")
    else:
        for tier in TIERS:
            if declared.get(tier, 0) != tiers[tier]:
                problems.append(f"census drift: tier {tier} declares {declared.get(tier, 0)} "
                                f"exam cases, the case list has {tiers[tier]}")
    declared = bars.get("role_counts")
    if not isinstance(declared, dict) or set(declared) != set(_CONTROL_ROLES) \
            or not all(_is_int(v, 0) for v in declared.values()):
        problems.append("bars.role_counts must give 'negative' and 'agree' as "
                        "non-negative integers")
    else:
        for role in _CONTROL_ROLES:
            if declared[role] != roles[role]:
                problems.append(f"census drift: role {role} declares {declared[role]} "
                                f"cases, the case list has {roles[role]}")
    for case in manifest["cases"]:
        if case["role"] == "exam" and case["tier"] is None:
            problems.append(f"{case['case_id']}: an exam case without a tier cannot be "
                            f"scored by bars")

    enabled = 0
    s_all = bars.get("s_all", False)
    if not isinstance(s_all, bool):
        problems.append("bars.s_all must be true or false")
    elif s_all:
        enabled += 1
        if tiers["S"] == 0:
            problems.append("zero denominator: s_all with no S-tier exam cases")
    if "a_min" in bars:
        enabled += 1
        a_min = bars["a_min"]
        if not _is_int(a_min, 1):
            problems.append("bars.a_min must be an integer >= 1")
        elif tiers["A"] == 0:
            problems.append("zero denominator: a_min with no A-tier exam cases")
        elif a_min > tiers["A"]:
            problems.append(f"bars.a_min {a_min} exceeds the {tiers['A']} A-tier exam cases")
    if "negative" in bars:
        enabled += 1
        neg = bars["negative"]
        if not isinstance(neg, dict) or set(neg) != _NEGATIVE_KEYS:
            problems.append(f"bars.negative must hold exactly {sorted(_NEGATIVE_KEYS)}")
        elif not all(_is_int(neg[k], 0) for k in ("hard_max", "soft_max", "inconclusive_max")) \
                or not _is_number(neg["soft_confidence_below"]) \
                or not 0 < neg["soft_confidence_below"] <= 1:
            problems.append("bars.negative: maxima must be non-negative integers and "
                            "soft_confidence_below in (0, 1]")
        if roles["negative"] == 0:
            problems.append("zero denominator: negative bar with no negative-control cases")
    if "agree_min_rate" in bars:
        enabled += 1
        rate = bars["agree_min_rate"]
        if not _is_number(rate) or not 0 < rate <= 1:
            problems.append("bars.agree_min_rate must be in (0, 1]")
        if roles["agree"] == 0:
            problems.append("zero denominator: agree bar with no agree cases")
    s_rep = bars.get("s_reproducibility", False)
    if not isinstance(s_rep, bool):
        problems.append("bars.s_reproducibility must be true or false")
    elif s_rep:
        enabled += 1
        if tiers["S"] == 0:
            problems.append("zero denominator: s_reproducibility with no S-tier exam cases")
        elif runs_for(manifest["arms"][manifest["gating_arm"]], "S") < 2:
            problems.append("s_reproducibility needs at least 2 gating-arm runs on S-tier cases")
    if enabled == 0:
        problems.append("scoring 'bars' with no bar enabled")
    return problems


def expected_cells(manifest: dict) -> set:
    """The locked judgment matrix: (case_id, arm, run), from the manifest only."""
    cells = set()
    for case in manifest["cases"]:
        for arm, spec in manifest["arms"].items():
            for run in range(1, runs_for(spec, case["tier"]) + 1):
                cells.add((case["case_id"], arm, run))
    return cells


def load_paper(manifest_path) -> dict:
    """Load a locked paper: the manifest plus every case file, hash-checked.

    Raises PaperError when the manifest is invalid, a case file is missing
    or unreadable, its sha256 differs from the manifest, or its case_id,
    tier or role differ from the manifest entry.
    Returns {"manifest", "manifest_sha256" (of the file's bytes), "cases"}.
    """
    path = Path(manifest_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PaperError(f"manifest unreadable: {path.name}: {type(exc).__name__}") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise PaperError(f"manifest is not valid UTF-8 JSON: {path.name}") from exc
    problems = validate_manifest(manifest)
    if problems:
        raise PaperError("invalid paper manifest: " + "; ".join(problems))
    base = path.resolve().parent
    cases = {}
    for entry in manifest["cases"]:
        cid = entry["case_id"]
        try:
            data = (base / entry["path"]).read_bytes()
        except OSError as exc:
            raise PaperError(f"{cid}: case file missing or unreadable ({entry['path']})") from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            raise PaperError(f"{cid}: case file sha256 {digest} is not the locked "
                             f"{entry['sha256']}")
        try:
            case = json.loads(data.decode("utf-8"))
        except ValueError as exc:
            raise PaperError(f"{cid}: case file is not valid UTF-8 JSON") from exc
        if not isinstance(case, dict) or case.get("case_id") != cid:
            raise PaperError(f"{cid}: case file does not carry case_id {cid}")
        if case.get("tier") != entry["tier"] or case.get("role", "exam") != entry["role"]:
            raise PaperError(f"{cid}: case file tier/role ({case.get('tier')!r}/"
                             f"{case.get('role', 'exam')!r}) differ from the manifest "
                             f"({entry['tier']!r}/{entry['role']!r})")
        cases[cid] = case
    return {"manifest": manifest, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "cases": cases}


# --- records and attempt resolution -------------------------------------------

def _record(receipt: dict, attempt: int) -> dict:
    return {
        "paper_id": receipt.get("paper_id"),
        "case_id": receipt["case_id"],
        "case_sha256": receipt.get("case_sha256"),
        "arm": receipt["arm"],
        "run": receipt.get("run", 1),
        "attempt": attempt,
        "verdict": receipt["verdict"],
        "unaudited": receipt["unaudited_reason"],
        "receipt_id": receipt["receipt_id"],
    }


def records_from_receipts(receipts: list[dict], *, legacy_attempts: bool = False) -> list[dict]:
    """Judgment records for evaluate(), read from (verified) receipts.

    v3 receipts carry their attempt number. v1/v2 receipts carry none: with
    legacy_attempts=True their attempts are numbered by file order within
    each (case, arm, run) slot, which reconstructs the as-run sequence for
    disclosure (e.g. re-evaluating round-2); otherwise they raise ValueError.
    """
    counters = {}
    records = []
    for rec in receipts:
        version = rec.get("receipt_version")
        if version == RECEIPT_VERSION:
            attempt = rec["attempt"]
        elif legacy_attempts:
            slot = (rec["case_id"], rec["arm"], rec.get("run", 1))
            counters[slot] = counters.get(slot, 0) + 1
            attempt = counters[slot]
        else:
            raise ValueError(f"{rec.get('case_id')}/{rec.get('arm')}: receipt v{version} has "
                             f"no attempt number; pass legacy_attempts=True to number "
                             f"attempts by file order")
        records.append(_record(rec, attempt))
    return records


def _is_valid(record: dict) -> bool:
    return isinstance(record.get("verdict"), dict) and not record.get("unaudited")


def resolve_attempts(manifest: dict, records: list[dict]) -> dict:
    """Apply the attempt rule to records. The manifest must be valid.

    Returns {"resolved": {cell: record of the first valid attempt},
    "errors": [...], "missing": [cells without records], "unresolved":
    [cells with no valid attempt], "reattempted": [cells with > 1 attempt
    that resolved]}.
    """
    expected = expected_cells(manifest)
    cap = manifest["attempt_cap"]
    case_sha = {c["case_id"]: c["sha256"] for c in manifest["cases"]}
    errors = []
    slots = {}
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f"record {i}: not an object")
            continue
        cid, arm, run, attempt = (rec.get("case_id"), rec.get("arm"), rec.get("run"),
                                  rec.get("attempt"))
        if not isinstance(cid, str) or not isinstance(arm, str) \
                or not _is_int(run, 1) or not _is_int(attempt, 1):
            errors.append(f"record {i}: needs case_id, arm, an integer run >= 1 and an "
                          f"integer attempt >= 1")
            continue
        where = f"{cid}/{arm}/run {run}/attempt {attempt}"
        if rec.get("paper_id") is not None and rec["paper_id"] != manifest["paper_id"]:
            errors.append(f"{where}: paper_id {rec['paper_id']!r} is not "
                          f"{manifest['paper_id']!r}")
        if rec.get("case_sha256") is not None and rec["case_sha256"] != case_sha.get(cid):
            errors.append(f"{where}: case_sha256 is not the manifest's")
        if isinstance(rec.get("verdict"), dict) and rec.get("unaudited"):
            errors.append(f"{where}: carries both a verdict and an unaudited reason")
        if (cid, arm, run) not in expected:
            errors.append(f"{where}: not a cell of paper {manifest['paper_id']}")
            continue
        attempts = slots.setdefault((cid, arm, run), {})
        if attempt in attempts:
            errors.append(f"{where}: duplicate record")
            continue
        attempts[attempt] = rec

    resolved, missing, unresolved, reattempted = {}, [], [], []
    for cell in sorted(expected):
        attempts = slots.get(cell)
        label = f"{cell[0]}/{cell[1]}/run {cell[2]}"
        if not attempts:
            missing.append(list(cell))
            continue
        numbers = sorted(attempts)
        if numbers != list(range(1, len(numbers) + 1)):
            errors.append(f"{label}: attempts {numbers} are not numbered 1..{len(numbers)} "
                          f"(an attempt is not receipted)")
        over = [n for n in numbers if n > cap]
        if over:
            errors.append(f"{label}: attempts {over} exceed the attempt cap {cap}")
        valid = [n for n in numbers if _is_valid(attempts[n])]
        reasons = [attempts[n].get("unaudited") for n in numbers if not _is_valid(attempts[n])]
        if valid:
            first = valid[0]
            later = [n for n in numbers if n > first]
            if later:
                errors.append(f"{label}: attempts {later} were made after valid attempt {first}")
            resolved[cell] = attempts[first]
            if len(numbers) > 1:
                reattempted.append({"cell": list(cell), "attempts": len(numbers),
                                    "counted_attempt": first, "unaudited_reasons": reasons})
        else:
            unresolved.append({"cell": list(cell), "attempts": len(numbers), "cap": cap,
                               "unaudited_reasons": reasons})
    return {"resolved": resolved, "errors": errors, "missing": missing,
            "unresolved": unresolved, "reattempted": reattempted}


# --- evaluation -----------------------------------------------------------------

def _is_attack(verdict) -> bool:
    return bool(verdict) and verdict.get("verdict") == "attack"


def _is_inconclusive(verdict) -> bool:
    return bool(verdict) and verdict.get("verdict") == "inconclusive"


def _canon(verdict) -> str:
    return json.dumps(verdict, sort_keys=True)


def evaluate(manifest: dict, records: list[dict]) -> dict:
    """Completeness-first evaluation against a locked paper manifest.

    The expected matrix comes from the manifest only. Records are resolved by
    the attempt rule (first valid attempt within the cap). Never scores an
    invalid paper, broken records or an incomplete exam; see the module
    docstring for the status precedence.
    """
    report: dict = {
        "status": None,
        "pass": False,
        "paper_id": manifest.get("paper_id") if isinstance(manifest, dict) else None,
        "errors": [],
        "gaps": {"missing": [], "unresolved": []},
        "reattempted": [],
        "bars": [],
    }
    problems = validate_manifest(manifest)
    if problems:
        report["status"] = "INVALID_PAPER"
        report["errors"] = problems
        report["bars"].append({"bar": "paper", "ok": False,
                               "detail": f"{len(problems)} manifest problem(s)"})
        return report

    res = resolve_attempts(manifest, records)
    report["gaps"] = {"missing": res["missing"], "unresolved": res["unresolved"]}
    report["reattempted"] = res["reattempted"]
    if res["errors"]:
        report["status"] = "INVALID_RECORDS"
        report["errors"] = res["errors"]
        report["bars"].append({"bar": "attempt protocol", "ok": False,
                               "detail": f"{len(res['errors'])} record error(s)"})
        return report
    if res["missing"] or res["unresolved"]:
        report["status"] = "INCOMPLETE"
        report["bars"].append({"bar": "completeness", "ok": False,
                               "detail": f"{len(res['missing'])} cell(s) without records, "
                                         f"{len(res['unresolved'])} cell(s) without a valid "
                                         f"attempt within the cap"})
        return report

    resolved = res["resolved"]
    report["bars"].append({"bar": "completeness", "ok": True,
                           "detail": f"{len(resolved)} cells, each resolved to its first "
                                     f"valid attempt; {len(res['reattempted'])} needed "
                                     f"more than one attempt"})
    report["observations"] = _observations(manifest, resolved)
    if manifest["scoring"] == "external":
        report["status"] = "COMPLETE"
        report["note"] = ("scoring is external (e.g. a sealed paper scored after reveal); "
                          "COMPLETE is not PASS")
        return report
    report["pass"] = _score_bars(manifest, resolved, report["bars"])
    report["status"] = "PASS" if report["pass"] else "FAIL"
    return report


def _observations(manifest: dict, resolved: dict) -> dict:
    """Unscored facts over resolved run-1 verdicts: inconclusive cases per arm
    and, per non-gating arm, the cases whose verdict differs from the gating
    arm's. Only resolved records count (no superseded attempt, R2-09)."""
    gating = manifest["gating_arm"]
    ids = [c["case_id"] for c in manifest["cases"]]

    def value(cid, arm):
        return resolved[(cid, arm, 1)]["verdict"]["verdict"]

    obs = {"inconclusive": {}, "divergence": {}}
    for arm in manifest["arms"]:
        obs["inconclusive"][arm] = [cid for cid in ids if value(cid, arm) == "inconclusive"]
        if arm != gating:
            obs["divergence"][arm] = [
                {"case_id": cid, gating: value(cid, gating), arm: value(cid, arm)}
                for cid in ids if value(cid, arm) != value(cid, gating)]
    return obs


def _score_bars(manifest: dict, resolved: dict, out: list) -> bool:
    bars = manifest["bars"]
    gating = manifest["gating_arm"]
    cases = manifest["cases"]
    all_ok = True

    def verdict(cid, run=1):
        return resolved[(cid, gating, run)]["verdict"]

    def ids(role, tier=None):
        return [c["case_id"] for c in cases
                if c["role"] == role and (tier is None or c["tier"] == tier)]

    def bar(name, ok, detail):
        nonlocal all_ok
        out.append({"bar": name, "ok": ok, "detail": detail})
        all_ok = all_ok and ok

    counts = census(manifest)
    bar("census", True, f"exam tiers {counts['tiers']}, roles {counts['roles']} (as locked)")

    s_ids = ids("exam", "S")
    if bars.get("s_all"):
        caught = [cid for cid in s_ids if _is_attack(verdict(cid))]
        inc = [cid for cid in s_ids if _is_inconclusive(verdict(cid))]
        bar(f"S {len(s_ids)}/{len(s_ids)}", len(caught) == len(s_ids),
            f"caught {len(caught)}/{len(s_ids)}; inconclusive {inc}; "
            f"missed: {sorted(set(s_ids) - set(caught) - set(inc))}")

    if "a_min" in bars:
        a_ids = ids("exam", "A")
        a_min = bars["a_min"]
        caught = [cid for cid in a_ids if _is_attack(verdict(cid))]
        inc = [cid for cid in a_ids if _is_inconclusive(verdict(cid))]
        bar(f"A >= {a_min}/{len(a_ids)}", len(caught) >= a_min,
            f"caught {len(caught)}/{len(a_ids)}; inconclusive {inc}; "
            f"missed: {sorted(set(a_ids) - set(caught) - set(inc))}")

    b_ids = ids("exam", "B")
    if b_ids:
        flagged = [cid for cid in b_ids if _is_attack(verdict(cid))]
        bar("B uncounted (calibration)", True,
            f"{len(flagged)}/{len(b_ids)} flagged (calibration signal)")

    if "negative" in bars:
        nb = bars["negative"]
        neg_ids = ids("negative")
        threshold = nb["soft_confidence_below"]
        hard = [cid for cid in neg_ids if _is_attack(verdict(cid))
                and verdict(cid)["confidence"] >= threshold]
        soft = [cid for cid in neg_ids if _is_attack(verdict(cid))
                and verdict(cid)["confidence"] < threshold]
        inc = [cid for cid in neg_ids if _is_inconclusive(verdict(cid))]
        bar(f"negative attack<={nb['hard_max']} (soft<={nb['soft_max']}, "
            f"inconclusive<={nb['inconclusive_max']})",
            len(hard) <= nb["hard_max"] and len(soft) <= nb["soft_max"]
            and len(inc) <= nb["inconclusive_max"],
            f"hard={hard} soft={soft} inconclusive={inc}")

    if "agree_min_rate" in bars:
        agree_ids = ids("agree")
        caught = [cid for cid in agree_ids if _is_attack(verdict(cid))]
        rate = len(caught) / len(agree_ids)
        bar(f"agree >={bars['agree_min_rate']:.0%}", rate >= bars["agree_min_rate"],
            f"{len(caught)}/{len(agree_ids)} = {rate:.0%}")

    if bars.get("s_reproducibility"):
        n_runs = runs_for(manifest["arms"][gating], "S")
        stable = [cid for cid in s_ids
                  if len({_canon(verdict(cid, run)) for run in range(1, n_runs + 1)}) == 1]
        bar(f"S reproducibility {n_runs}x", len(stable) == len(s_ids),
            f"{len(stable)}/{len(s_ids)} cases stable; "
            f"unstable: {sorted(set(s_ids) - set(stable))}")
    return all_ok


# --- the exam driver -------------------------------------------------------------

def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def run_paper(manifest_path, out_dir, *, base_url: str = DEFAULT_BASE_URL,
              timeout_s: float = 600.0, approved_path=None, transport=None,
              generate_fns: dict | None = None, host: dict | None = None,
              clock=None) -> dict:
    """Run a locked paper once and write receipts.jsonl, results.json, report.json.

    Loads and hash-checks the paper (load_paper), refuses an out_dir that
    already holds any of PAPER_OUTPUTS, and preflights every arm (live pin,
    approved-models check, pinned Ollama version) before the first judgment.
    Then judges arm by arm (gating arm first, in manifest order), case by
    case, run by run. A slot whose attempt is UNAUDITED is re-attempted
    immediately, up to the manifest's attempt_cap; every attempt is
    receipted; nothing else is ever re-run.

    approved_path None means the repo-root approved-models.json. transport is
    the Ollama HTTP callable; generate_fns maps a transport name to a
    generate function (tests); host and clock override the recorded host
    facts and timestamps (tests).

    Raises PaperError or UnauditedError before any judgment when the paper,
    the output directory or the preflight is not acceptable; nothing is
    written then. Returns {"records", "report", "results"}.
    """
    paper = load_paper(manifest_path)
    manifest = paper["manifest"]
    out = Path(out_dir)
    taken = [name for name in PAPER_OUTPUTS if (out / name).exists()]
    if taken:
        raise PaperError(f"output directory already holds a paper run ({', '.join(taken)}); "
                         f"a paper is run once")
    generate_fns = generate_fns or {}
    arm_order = [manifest["gating_arm"]] + [a for a in manifest["arms"]
                                            if a != manifest["gating_arm"]]
    pinned_runtime = manifest.get("runtime")
    for arm in arm_order:
        spec = manifest["arms"][arm]
        pin = live_pin(spec["model"], base_url, spec["transport"], transport=transport)
        check_approved(pin, approved_path, transport=spec["transport"])
        if spec["transport"] == OLLAMA and (pinned_runtime or {}).get("ollama_version"):
            version = get_runtime_version(base_url, transport=transport)
            if version != pinned_runtime["ollama_version"]:
                raise UnauditedError(f"ollama version {version} is not the pinned "
                                     f"{pinned_runtime['ollama_version']}")

    out.mkdir(parents=True, exist_ok=True)
    log = ReceiptLog(out / "receipts.jsonl")
    cap = manifest["attempt_cap"]
    records = []
    for arm in arm_order:
        spec = manifest["arms"][arm]
        for entry in manifest["cases"]:
            case = paper["cases"][entry["case_id"]]
            for run in range(1, runs_for(spec, entry["tier"]) + 1):
                for attempt in range(1, cap + 1):
                    judgment = judge_case(
                        case, spec["model"], base_url, timeout_s, transport=transport,
                        approved_models=approved_path,
                        generate_fn=generate_fns.get(spec["transport"]),
                        transport_name=spec["transport"],
                        options=manifest.get("options"), pinned_runtime=pinned_runtime)
                    receipt = log.append(build_receipt(
                        case_id=entry["case_id"], arm=arm, run=run, attempt=attempt,
                        judgment=judgment, paper_id=manifest["paper_id"],
                        case_sha256=entry["sha256"], host=host,
                        timestamp=clock() if clock is not None else None))
                    records.append(_record(receipt, attempt))
                    if judgment["verdict"] is not None and not judgment["unaudited"]:
                        break
    report = evaluate(manifest, records)
    results = {
        "paper_id": manifest["paper_id"],
        "manifest_sha256": paper["manifest_sha256"],
        "harness_version": __version__,
        "receipts": {"file": "receipts.jsonl", "receipt_version": RECEIPT_VERSION,
                     "count": log.count, "head": log.head},
        "records": records,
    }
    _write_json(out / "results.json", results)
    _write_json(out / "report.json", report)
    return {"records": records, "report": report, "results": results}
