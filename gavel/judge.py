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
  daemon-reported truncation is UNAUDITED.
- CR-07: UnauditedError carries any raw text the model returned, so the
  receipt can keep it.
- CR-17: extract_json is strict: the whole output must be one JSON object, or
  exactly one fenced block that is the whole output. extract_json_v2 keeps
  the round-2 extractor for verifying v2 receipts only.
"""

import http.client
import json
import re
import urllib.error
import urllib.request

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
    """

    def __init__(self, reason: str, raw: str | None = None,
                 generation: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.raw = raw
        self.generation = generation


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


def check_approved(pin: dict, approved_path, transport: str = "ollama") -> None:
    """Compare a live pin against the approved-models manifest.

    A model whose tag+digest (or, for cloud arms, tag alone) is not in the
    approved manifest is UNAUDITED. This is the enforceable half of pinning;
    recording a digest without comparing it proves nothing.
    """
    approved = json.loads(open(approved_path, encoding="utf-8").read())
    for entry in approved.get("approved", []):
        if entry.get("model") != pin.get("model"):
            continue
        want_digest = entry.get("manifest_digest")
        if want_digest is None:  # cloud arm: identity = model id + transport
            if entry.get("transport", transport) == transport:
                return
            continue
        if pin.get("manifest_digest") == want_digest:
            return
    raise UnauditedError(
        f"model/pin not in approved manifest: {pin.get('model')} "
        f"digest={pin.get('manifest_digest')}")


def _request_json(method: str, url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


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
    unreachable or answers malformed JSON (CR-14), when the context was full
    or the output stopped at a length limit (CR-16), or when the text is
    empty.
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
    if isinstance(prompt_tokens, int) and not isinstance(prompt_tokens, bool) \
            and prompt_tokens >= opts["num_ctx"]:
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


def agy_generate(model: str, prompt: str, base_url: str = "", timeout_s: float = 600,
                 transport=None, options: dict | None = None) -> dict:
    """Cloud-arm transport: one Antigravity CLI (agy) headless call.

    Cloud verdicts are recorded, never gating (PREREG Addendum 4): no local
    digest exists, so the approved-models manifest matches on model id.
    Returns {"raw": stdout, "generation": {}} (the transport protocol shared
    with generate). options are not applicable to this transport.
    """
    import os
    import subprocess

    exe = os.environ.get("GAVEL_AGY",
                         str(os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")))
    try:
        proc = subprocess.run([exe, "-p", prompt, "--model", model],
                              capture_output=True, text=True,
                              timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise UnauditedError(f"agy timeout after {timeout_s}s") from exc
    except OSError as exc:
        raise UnauditedError(f"agy unreachable: {exc}") from exc
    if proc.returncode != 0:
        raise UnauditedError(f"agy exit {proc.returncode}: {proc.stderr[:200]}",
                             raw=proc.stdout or None)
    if not proc.stdout.strip():
        raise UnauditedError("empty agy response", raw=proc.stdout)
    return {"raw": proc.stdout, "generation": {}}


_WHOLE_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*)\r?\n[ \t]*```", re.DOTALL)


def _strict_loads(body: str):
    def no_duplicate_keys(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate key {key!r}")
            obj[key] = value
        return obj

    def no_constants(name):
        raise ValueError(f"non-standard JSON constant {name}")

    return json.loads(body, object_pairs_hook=no_duplicate_keys,
                      parse_constant=no_constants)


def extract_json(text: str) -> dict:
    """Extract the verdict JSON. Strict and narrow (CR-17); anything else fails.

    Accepted, after stripping surrounding whitespace: the whole output is one
    JSON object; or the whole output is exactly one fenced block (```json or
    ```) whose body is one JSON object. Rejected: prose before or after the
    object or the fence, a second fence, duplicate keys, NaN/Infinity.
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
        obj = _strict_loads(body)
    except ValueError as exc:
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


def approved_model_entry(model: str, approved_path) -> dict | None:
    approved = json.loads(open(approved_path, encoding="utf-8").read())
    for entry in approved.get("approved", []):
        if entry.get("model") == model:
            return entry
    return None
