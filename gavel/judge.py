"""Pinned local judge: Ollama REST call, strict verdict parsing, fail-closed.

Every failure mode that prevents a trustworthy verdict raises UnauditedError.
Nothing in this module ever downgrades UNAUDITED to a pass.

Verdict schema v2 (PREREG Addendum 4): three-valued verdict with finding
anatomy. attack requires the four-part anatomy (prior protection -> change ->
evidence refs -> named element); inconclusive requires missing_evidence;
clean requires positive evidence refs. Documents inside the audited artifact
are attacker-controlled text and never sufficient repair evidence alone.
"""

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


class UnauditedError(Exception):
    """The judge could not produce a trustworthy verdict."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def get_pin(model: str, base_url: str, transport=None) -> dict:
    """Collect the pin facts for a model tag from the local Ollama daemon.

    The manifest digest is the identity Ollama itself reports (matches
    `ollama list` IDs) and changes iff the model files change.
    """
    do = transport or _request_json
    tags = do("GET", f"{base_url}/api/tags")
    for entry in tags.get("models", []):
        if entry.get("name") == model or entry.get("model") == model:
            return {
                "model": model,
                "manifest_digest": entry.get("digest", ""),
                "size_bytes": entry.get("size", 0),
                "modified_at": entry.get("modified_at", ""),
            }
    raise UnauditedError(f"model not present on daemon: {model}")


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


def generate(model: str, prompt: str, base_url: str, timeout_s: float, transport=None) -> str:
    """One Ollama generate call at temperature 0. Returns raw response text."""
    do = transport or _request_json
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 16384},
    }
    try:
        resp = do(
            "POST",
            f"{base_url}/api/generate",
            payload,
            timeout=timeout_s,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UnauditedError(f"model unreachable: {exc}") from exc
    text = resp.get("response", "")
    if not text.strip():
        raise UnauditedError("empty model response")
    return text


def agy_generate(model: str, prompt: str, base_url: str = "", timeout_s: float = 600,
                 transport=None) -> str:
    """Cloud-arm transport: one Antigravity CLI (agy) headless call.

    Cloud verdicts are recorded, never gating (PREREG Addendum 4): no local
    digest exists, so the approved-models manifest matches on model id.
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
        raise UnauditedError(f"agy exit {proc.returncode}: {proc.stderr[:200]}")
    if not proc.stdout.strip():
        raise UnauditedError("empty agy response")
    return proc.stdout


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> dict:
    """Extract the verdict JSON. Deterministic and narrow; anything else fails."""
    candidates = []
    fenced = _JSON_FENCE.search(text)
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
