"""Pinned local judge: Ollama REST call, strict verdict parsing, fail-closed.

Every failure mode that prevents a trustworthy verdict raises UnauditedError.
Nothing in this module ever downgrades UNAUDITED to a pass.

Verdict schema v2 (PREREG Addendum 4): three-valued verdict with finding
anatomy. attack requires the four-part anatomy (prior protection -> change ->
evidence refs -> named element); inconclusive requires missing_evidence;
clean requires positive evidence refs. Documents inside the audited artifact
are attacker-controlled text and never sufficient repair evidence alone.

Exam-validity fixes (takeover audit 2026-10-15):
- CR-14: every transport failure (URLError, TimeoutError, OSError,
  HTTPException, JSON or Unicode decode errors) becomes UnauditedError; none
  escapes as an unhandled exception.
- CR-16: the context size (num_ctx) is explicit and returned for the receipt;
  a full context (prompt_eval_count >= num_ctx), a length stop or a
  daemon-reported truncation is UNAUDITED. So is a response without a
  positive integer prompt_eval_count: without it truncation cannot be
  excluded. The guard sees only what the daemon reports; if the daemon
  counts only the prompt tokens it did not take from its cache, a full
  context can still go unseen (judge-smoke records whether it does).
- CR-07: UnauditedError carries any raw text the model returned, so the
  receipt can keep it.
- CR-17: extract_json is strict: the whole output must be one JSON object, or
  exactly one fenced block that is the whole output. extract_json_v2 keeps
  the round-2 extractor for verifying v2 receipts only. strict_loads (no
  duplicate keys, no NaN/Infinity) also reads every locked input: paper
  manifests, case files, receipts lines, JSON answer keys, results.json,
  approved-models.json and daemon responses.
- CR-02/CR-15/F4: the approved-models manifest defaults to the file at the
  root of the repository that holds this package (never the working
  directory); a missing, unreadable or malformed manifest is UNAUDITED; an
  entry with a null digest approves only an explicitly declared cloud
  transport. The caller (qualify.judge_case) checks it on every judgment.
  check_approved returns the name and sha256 of the manifest it checked
  against, which receipts and results.json record.
- CR-08/CR-09/CR-13: the agy transport resolves and hashes its executable,
  runs it without a shell in an empty temporary directory, guards the
  command-line size, enforces its timeout without blocking on pipes, and
  decodes strictly; see the block comment above agy_generate.
"""

import hashlib
import http.client
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SCHEMA_VERSION = 2

VERDICT_VALUES = ("attack", "clean", "inconclusive")

VERDICT_KEYS = {
    "verdict", "mechanism_class", "offending_element", "confidence",
    "rationale", "prior_protection", "change_summary", "evidence_refs",
    "missing_evidence",
}

ATTACK_REQUIRED_NONEMPTY = (
    "offending_element", "prior_protection", "change_summary", "evidence_refs",
)

OLLAMA = "ollama"
# Transports with no local model digest. An approved-models entry with a
# null digest is valid only for one of these, named explicitly (CR-15).
CLOUD_TRANSPORTS = frozenset({"agy"})
APPROVED_MODELS_FILENAME = "approved-models.json"
DEFAULT_NUM_CTX = 16384
DEFAULT_OPTIONS = {"temperature": 0, "num_ctx": DEFAULT_NUM_CTX}
OPTION_KEYS = ("temperature", "num_ctx", "seed")

# Facts about one generate call that go into the receipt (CR-16).
GENERATION_KEYS = ("prompt_eval_count", "eval_count", "done", "done_reason", "truncated")

# Everything a transport call can raise that means "no trustworthy answer"
# (CR-14). URLError and TimeoutError are OSError subclasses; they are listed
# for the reader. ValueError covers json.JSONDecodeError and
# UnicodeDecodeError.
TRANSPORT_ERRORS = (urllib.error.URLError, TimeoutError, OSError,
                    http.client.HTTPException, ValueError)


class UnauditedError(Exception):
    """The judge could not produce a trustworthy verdict.

    raw: model output received before the failure, if any (kept in the
    receipt, CR-07). generation: generate-call facts, if any (CR-16).
    transport_version: what the transport knew about itself before it
    failed (for agy: the executable and its sha256, CR-08), if anything.
    """

    def __init__(self, reason: str, raw: str | None = None,
                 generation: dict | None = None, transport_version=None):
        super().__init__(reason)
        self.reason = reason
        self.raw = raw
        self.generation = generation
        self.transport_version = transport_version


def _describe(exc: BaseException) -> str:
    text = str(exc)
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def get_pin(model: str, base_url: str, transport=None) -> dict:
    """Collect the pin facts for a model tag from the local Ollama daemon.

    The manifest digest is the identity Ollama itself reports (matches
    `ollama list` IDs) and changes iff the model files change. Any daemon
    failure is UNAUDITED (CR-14).
    """
    do = transport or _request_json
    try:
        tags = do("GET", f"{base_url}/api/tags")
    except TRANSPORT_ERRORS as exc:
        raise UnauditedError(f"daemon unreachable while reading the model pin: "
                             f"{_describe(exc)}") from exc
    if not isinstance(tags, dict) or not isinstance(tags.get("models", []), list):
        raise UnauditedError("malformed /api/tags response")
    for entry in tags.get("models", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == model or entry.get("model") == model:
            digest = entry.get("digest")
            if not isinstance(digest, str) or not digest:
                raise UnauditedError(f"daemon reported no digest for {model}")
            return {
                "model": model,
                "manifest_digest": digest,
                "size_bytes": entry.get("size", 0),
                "modified_at": entry.get("modified_at", ""),
            }
    raise UnauditedError(f"model not present on daemon: {model}")


def get_runtime_version(base_url: str, transport=None) -> str:
    """The Ollama daemon version from /api/version (recorded in receipts)."""
    do = transport or _request_json
    try:
        resp = do("GET", f"{base_url}/api/version")
    except TRANSPORT_ERRORS as exc:
        raise UnauditedError(f"daemon unreachable while reading its version: "
                             f"{_describe(exc)}") from exc
    version = resp.get("version") if isinstance(resp, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise UnauditedError("daemon reported no version")
    return version


def live_pin(model: str, base_url: str, transport_name: str = OLLAMA,
             transport=None) -> dict:
    """The pin of a model as it is right now.

    Ollama: read from the daemon (get_pin). Cloud transports have no local
    digest; their pin is the model id plus the transport name.
    """
    if transport_name == OLLAMA:
        return get_pin(model, base_url, transport=transport)
    if transport_name in CLOUD_TRANSPORTS:
        return {"model": model, "manifest_digest": None, "transport": transport_name}
    raise UnauditedError(f"unknown transport: {transport_name!r}")


def default_approved_path() -> Path:
    """approved-models.json at the root of the repository holding this package.

    Resolved from this file's location, never from the working directory
    (CR-02). A copy of the package without that file fails closed.
    """
    return Path(__file__).resolve().parent.parent / APPROVED_MODELS_FILENAME


def read_approved(approved_path=None) -> tuple[dict, dict]:
    """Read the approved-models manifest; None means default_approved_path().

    Returns (manifest, identity), where identity is {"file": the file name,
    "sha256": sha256 of the bytes that were parsed}. A missing, unreadable,
    non-JSON (strict_loads) or malformed manifest is UNAUDITED. Reasons name
    the file, not its directory, because they go into receipts.
    """
    path = Path(approved_path) if approved_path is not None else default_approved_path()
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, ValueError) as exc:
        raise UnauditedError(f"approved-models manifest unreadable ({path.name}): "
                             f"{type(exc).__name__}") from exc
    try:
        data = strict_loads(text)
    except (ValueError, RecursionError) as exc:
        raise UnauditedError(f"approved-models manifest is not valid JSON ({path.name})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("approved"), list):
        raise UnauditedError(f"approved-models manifest malformed ({path.name}): "
                             f"no 'approved' list")
    return data, {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()}


def load_approved(approved_path=None) -> dict:
    """The approved-models manifest (read_approved without the identity)."""
    return read_approved(approved_path)[0]


def check_approved(pin: dict, approved_path=None, transport: str = OLLAMA) -> dict:
    """Compare a live pin against the approved-models manifest.

    A model whose tag+digest (or, for cloud arms, tag alone) is not in the
    approved manifest is UNAUDITED. This is the enforceable half of pinning;
    recording a digest without comparing it proves nothing.

    approved_path None means default_approved_path() (repo root, not CWD).
    An entry with a digest approves only that exact digest, for its declared
    transport (an entry without a transport field is a local Ollama entry).
    An entry with a null or missing digest approves only a pin without a
    digest, and only when the entry names a cloud transport explicitly and
    that transport is the one in use (CR-15).

    Returns the identity of the manifest that approved the pin ({"file",
    "sha256"}, see read_approved), so callers can record which file gated
    the judgment.
    """
    approved, identity = read_approved(approved_path)
    model = pin.get("model")
    digest = pin.get("manifest_digest")
    for entry in approved["approved"]:
        if not isinstance(entry, dict) or entry.get("model") != model:
            continue
        entry_transport = entry.get("transport")
        want_digest = entry.get("manifest_digest")
        if want_digest is None:  # cloud arm: identity = model id + transport
            if entry_transport in CLOUD_TRANSPORTS and entry_transport == transport \
                    and digest is None:
                return identity
            continue
        if (entry_transport or OLLAMA) != transport:
            continue
        if isinstance(want_digest, str) and want_digest and digest == want_digest:
            return identity
    raise UnauditedError(
        f"model/pin not in approved manifest: {model} "
        f"digest={digest} transport={transport}")


def _request_json(method: str, url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return strict_loads(resp.read().decode())


def resolve_options(options: dict | None = None) -> dict:
    """Generation options sent to Ollama: defaults plus the given overrides.

    Only temperature, num_ctx and seed are accepted; anything else, or a
    num_ctx that is not a positive integer, is UNAUDITED.
    """
    opts = dict(DEFAULT_OPTIONS)
    for key, value in (options or {}).items():
        if key not in OPTION_KEYS:
            raise UnauditedError(f"unsupported generation option: {key!r}")
        opts[key] = value
    num_ctx = opts["num_ctx"]
    if not isinstance(num_ctx, int) or isinstance(num_ctx, bool) or num_ctx <= 0:
        raise UnauditedError(f"num_ctx must be a positive integer: {num_ctx!r}")
    return opts


def generate(model: str, prompt: str, base_url: str, timeout_s: float, transport=None,
             options: dict | None = None) -> dict:
    """One non-streaming Ollama generate call.

    Returns {"raw": text, "generation": {...}} where generation holds the
    daemon's prompt_eval_count, eval_count, done and done_reason. Raises
    UnauditedError (carrying any text received) when the daemon is
    unreachable or answers malformed JSON (CR-14), when the context was full,
    the output stopped at a length limit or the daemon reported no positive
    integer prompt_eval_count (CR-16: truncation cannot be excluded then),
    or when the text is empty.
    """
    do = transport or _request_json
    opts = resolve_options(options)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": opts,
    }
    try:
        resp = do(
            "POST",
            f"{base_url}/api/generate",
            payload,
            timeout=timeout_s,
        )
    except TRANSPORT_ERRORS as exc:
        raise UnauditedError(f"model unreachable: {_describe(exc)}") from exc
    if not isinstance(resp, dict):
        raise UnauditedError("malformed generate response: not a JSON object")
    generation = {key: resp[key] for key in GENERATION_KEYS if key in resp}
    text = resp.get("response")
    raw = text if isinstance(text, str) else None
    if resp.get("error"):
        raise UnauditedError(f"daemon error: {resp['error']}", raw=raw, generation=generation)
    if raw is None:
        raise UnauditedError("malformed generate response: no response text",
                             generation=generation)
    echoed = resp.get("model")
    if echoed is not None and echoed != model:
        raise UnauditedError(f"daemon answered as model {echoed!r}, requested {model!r}",
                             raw=raw, generation=generation)
    if resp.get("done") is False:
        raise UnauditedError("generation not done", raw=raw, generation=generation)
    if resp.get("truncated") is True:
        raise UnauditedError("daemon reported the prompt as truncated",
                             raw=raw, generation=generation)
    prompt_tokens = resp.get("prompt_eval_count")
    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool) \
            or prompt_tokens <= 0:
        raise UnauditedError(
            f"daemon reported no prompt_eval_count (got {prompt_tokens!r}, need a "
            f"positive integer); truncation cannot be excluded",
            raw=raw, generation=generation)
    if prompt_tokens >= opts["num_ctx"]:
        raise UnauditedError(
            f"context full: prompt_eval_count {prompt_tokens} >= num_ctx "
            f"{opts['num_ctx']}; the prompt may have been truncated",
            raw=raw, generation=generation)
    if resp.get("done_reason") == "length":
        raise UnauditedError("generation stopped at the length limit; output truncated",
                             raw=raw, generation=generation)
    if not raw.strip():
        raise UnauditedError("empty model response", raw=raw, generation=generation)
    return {"raw": raw, "generation": generation}


# --- agy (informed, cloud) transport -------------------------------------------
#
# Takeover audit 2026-10-15, CR-08/CR-09/CR-13. What this transport does and
# does not establish:
# - The executable is resolved explicitly: GAVEL_AGY (an absolute path) or
#   %LOCALAPPDATA%\agy\bin\agy.exe. No PATH lookup, no relative path, and
#   never a .bat/.cmd file (cmd.exe would parse the evidence text; on Windows
#   only an .exe is accepted). Its path (home directory shown as "~") and the
#   sha256 of its bytes are returned as the transport version and recorded
#   in every receipt, also when the call fails.
# - It runs with shell=False, stdin from the null device, and cwd set to a
#   fresh empty temporary directory, never the repository, so no case file or
#   answer key is reachable through a relative path. This is not a sandbox:
#   agy's own tool and file-access settings still apply and are not verified
#   here.
# - The prompt is still passed as the "-p" argument, as in round-2. A prompt
#   whose command line would exceed the Windows limit is UNAUDITED before
#   anything is started. TODO(pool): passing the prompt on stdin instead of
#   argv needs verification against agy on the pool before it is used; no
#   unverified agy flag is added here.
# - stdout and stderr go to temporary files, not pipes, so a grandchild that
#   keeps a handle open cannot block the harness. On timeout the direct child
#   is killed and the call is UNAUDITED; a grandchild may outlive it.
# - The output is decoded as UTF-8, strictly; invalid bytes are UNAUDITED
#   (the raw text is kept with backslash escapes).
# - Not established: which model agy actually used (it may fall back to a
#   default model), and agy's own version string. The executable sha256 is
#   the identity recorded.

AGY_MAX_COMMAND_UNITS = 32000  # Windows CreateProcess limit is 32767 UTF-16 units
AGY_KILL_GRACE_S = 5.0
_SHELL_SCRIPT_SUFFIXES = (".bat", ".cmd")
_popen = subprocess.Popen  # tests replace this; nothing else does


def _display_path(path: Path) -> str:
    """The path with the user's home directory written as "~" (receipts may be
    published; the account name is not evidence)."""
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except (ValueError, RuntimeError, KeyError, OSError):
        return path.as_posix()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_agy_executable() -> dict:
    """Locate the agy executable and describe it for the receipt.

    Returns {"executable": display path, "executable_sha256": hex,
    "executable_source": "GAVEL_AGY" | "default", "path": resolved Path}.
    Raises UnauditedError when it is not configured, not an absolute path,
    missing, a shell script, or (on Windows) not an .exe.
    """
    override = os.environ.get("GAVEL_AGY")
    if override:
        raw, source = override, "GAVEL_AGY"
    else:
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            raise UnauditedError("agy executable not configured: set GAVEL_AGY to its "
                                 "absolute path")
        raw, source = str(Path(base) / "agy" / "bin" / "agy.exe"), "default"
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise UnauditedError(f"agy executable must be an absolute path ({source})")
    suffix = candidate.suffix.lower()
    if suffix in _SHELL_SCRIPT_SUFFIXES or (os.name == "nt" and suffix != ".exe"):
        raise UnauditedError(f"agy executable {candidate.name!r} is not accepted ({source}): "
                             f"a .bat/.cmd script is never run, and on Windows only an "
                             f".exe is")
    try:
        path = candidate.resolve(strict=True)
        if not path.is_file():
            raise FileNotFoundError(str(candidate))
        digest = _file_sha256(path)
    except OSError as exc:
        raise UnauditedError(f"agy executable missing or unreadable ({source}): "
                             f"{type(exc).__name__}") from exc
    if path.suffix.lower() in _SHELL_SCRIPT_SUFFIXES:
        raise UnauditedError(f"agy executable resolves to a shell script ({source})")
    return {"executable": _display_path(path), "executable_sha256": digest,
            "executable_source": source, "path": path}


def _command_units(argv: list[str]) -> int:
    """Length of the Windows command line for argv, in UTF-16 code units."""
    return len(subprocess.list2cmdline(argv).encode("utf-16-le")) // 2


def _scrub(text: str) -> str:
    try:
        home = str(Path.home())
    except (RuntimeError, KeyError, OSError):
        return text
    return text.replace(home, "~") if home else text


def agy_generate(model: str, prompt: str, base_url: str = "", timeout_s: float = 600,
                 transport=None, options: dict | None = None) -> dict:
    """Cloud-arm transport: one Antigravity CLI (agy) headless call.

    Cloud verdicts are recorded, never gating (PREREG Addendum 4): no local
    digest exists, so the approved-models manifest matches on model id.
    Returns {"raw": stdout, "generation": {"exit_code"}, "transport_version":
    {...}} (the transport protocol shared with generate). base_url,
    transport and options do not apply to this transport and are ignored.
    Every failure is UnauditedError carrying the transport version when the
    executable was resolved. See the block comment above for what this
    transport does and does not establish.
    """
    exe = resolve_agy_executable()
    version = {key: exe[key] for key in ("executable", "executable_sha256",
                                         "executable_source")}
    version.update(cwd="fresh empty temporary directory", prompt_channel="argv",
                   stdin="null device")
    argv = [str(exe["path"]), "-p", prompt, "--model", model]
    units = _command_units(argv)
    if units > AGY_MAX_COMMAND_UNITS:
        raise UnauditedError(f"prompt too long for the agy argv transport: command line "
                             f"{units} UTF-16 units > {AGY_MAX_COMMAND_UNITS}",
                             transport_version=version)
    with tempfile.TemporaryDirectory(prefix="gavel-agy-", ignore_cleanup_errors=True) as workdir, \
            tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = _popen(argv, cwd=workdir, shell=False, stdin=subprocess.DEVNULL,
                          stdout=out, stderr=err)
        except (OSError, ValueError) as exc:
            raise UnauditedError(f"agy could not be started: {type(exc).__name__}",
                                 transport_version=version) from exc
        try:
            code = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            try:
                proc.kill()
                proc.wait(timeout=AGY_KILL_GRACE_S)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise UnauditedError(f"agy timeout after {timeout_s}s (process killed)",
                                 transport_version=version) from exc
        out.seek(0)
        stdout = out.read()
        err.seek(0)
        stderr = err.read()
    generation = {"exit_code": code}
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnauditedError("agy output is not valid UTF-8 (raw kept with backslash "
                             "escapes)", raw=stdout.decode("utf-8", "backslashreplace"),
                             generation=generation, transport_version=version) from exc
    if code != 0:
        tail = _scrub(stderr.decode("utf-8", "replace"))[:200]
        raise UnauditedError(f"agy exit {code}: {tail}", raw=text or None,
                             generation=generation, transport_version=version)
    if not text.strip():
        raise UnauditedError("empty agy response", raw=text, generation=generation,
                             transport_version=version)
    return {"raw": text, "generation": generation, "transport_version": version}


_WHOLE_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*)\r?\n[ \t]*```", re.DOTALL)


def strict_loads(body: str):
    """json.loads that refuses what a plain reader would silently accept.

    Raises ValueError for invalid JSON, a duplicate key in any object (a
    plain reader keeps the last one, so two readers can see different
    values), the non-standard constants NaN, Infinity and -Infinity, and
    nesting too deep to parse (RecursionError is converted).
    """
    def no_duplicate_keys(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate key {key!r}")
            obj[key] = value
        return obj

    def no_constants(name):
        raise ValueError(f"non-standard JSON constant {name}")

    try:
        return json.loads(body, object_pairs_hook=no_duplicate_keys,
                          parse_constant=no_constants)
    except RecursionError as exc:
        raise ValueError("JSON nested too deeply to parse") from exc


def extract_json(text: str) -> dict:
    """Extract the verdict JSON. Strict and narrow (CR-17); anything else fails.

    Accepted, after stripping surrounding whitespace: the whole output is one
    JSON object; or the whole output is exactly one fenced block (```json or
    ```) whose body is one JSON object. Rejected: prose before or after the
    object or the fence, a second fence, duplicate keys, NaN/Infinity,
    nesting too deep to parse.
    """
    if not isinstance(text, str):
        raise UnauditedError("model output is not text")
    stripped = text.strip()
    if stripped.startswith("```"):
        fenced = _WHOLE_FENCE.fullmatch(stripped)
        if fenced is None:
            raise UnauditedError("fenced output is not exactly one fenced JSON block")
        body = fenced.group(1).strip()
        if "```" in body:
            raise UnauditedError("more than one fenced block in the output")
    else:
        body = stripped
    if not (body.startswith("{") and body.endswith("}")):
        raise UnauditedError("output is not exactly one JSON object")
    try:
        obj = strict_loads(body)
    except (ValueError, RecursionError) as exc:
        raise UnauditedError(f"no parseable JSON verdict in response: {exc}") from exc
    if not isinstance(obj, dict):
        raise UnauditedError("verdict JSON is not an object")
    return obj


_JSON_FENCE_V2 = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json_v2(text: str) -> dict:
    """The round-2 (receipt v2) extractor, unchanged.

    Used only to re-parse the raw output of v2 receipts during content
    verification, so they are checked by the rules they were written under.
    Never used to judge.
    """
    candidates = []
    fenced = _JSON_FENCE_V2.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise UnauditedError("no parseable JSON verdict in response")


def validate_verdict(obj: dict, mechanism_classes: list[str]) -> dict:
    """Strict schema-v2 validation. Any deviation is UNAUDITED, never coerced.

    Semantics:
    - verdict "attack": mechanism_class in the closed list, offending_element
      named, and the anatomy fields prior_protection / change_summary /
      evidence_refs all non-empty; missing_evidence empty.
    - verdict "clean": mechanism_class and offending_element empty, but
      evidence_refs non-empty (positive grounds, not absence of findings);
      missing_evidence empty.
    - verdict "inconclusive": mechanism_class and offending_element empty;
      missing_evidence non-empty (what evidence would resolve it).
    """
    if set(obj.keys()) != VERDICT_KEYS:
        raise UnauditedError(f"verdict keys mismatch: {sorted(obj.keys())}")
    for key in ("verdict", "mechanism_class", "offending_element", "rationale",
                "prior_protection", "change_summary", "evidence_refs", "missing_evidence"):
        if not isinstance(obj[key], str):
            raise UnauditedError(f"{key} must be string")
    if obj["verdict"] not in VERDICT_VALUES:
        raise UnauditedError(f"verdict must be one of {VERDICT_VALUES}: {obj['verdict']!r}")
    if not isinstance(obj["confidence"], (int, float)) or isinstance(obj["confidence"], bool):
        raise UnauditedError("confidence must be number")
    if not 0.0 <= obj["confidence"] <= 1.0:
        raise UnauditedError("confidence out of range")
    if obj["verdict"] == "attack":
        if obj["mechanism_class"] not in mechanism_classes:
            raise UnauditedError(f"mechanism_class not in closed list: {obj['mechanism_class']!r}")
        for key in ATTACK_REQUIRED_NONEMPTY:
            if not obj[key].strip():
                raise UnauditedError(f"attack requires non-empty {key}")
        if obj["missing_evidence"] != "":
            raise UnauditedError("attack requires empty missing_evidence")
    elif obj["verdict"] == "clean":
        if obj["mechanism_class"] != "" or obj["offending_element"] != "" \
                or obj["prior_protection"] != "" or obj["change_summary"] != "":
            raise UnauditedError("clean requires empty mechanism/element/anatomy fields")
        if obj["missing_evidence"] != "":
            raise UnauditedError("clean requires empty missing_evidence")
        if not obj["evidence_refs"].strip():
            raise UnauditedError("clean requires positive evidence_refs")
    else:  # inconclusive
        if obj["mechanism_class"] != "" or obj["offending_element"] != "":
            raise UnauditedError("inconclusive requires empty mechanism_class and offending_element")
        if not obj["missing_evidence"].strip():
            raise UnauditedError("inconclusive requires non-empty missing_evidence")
    return obj


def approved_model_entry(model: str, approved_path=None) -> dict | None:
    approved = load_approved(approved_path)
    for entry in approved["approved"]:
        if isinstance(entry, dict) and entry.get("model") == model:
            return entry
    return None
