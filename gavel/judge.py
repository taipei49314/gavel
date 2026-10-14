"""Pinned local judge: Ollama REST call, strict verdict parsing, fail-closed.

Every failure mode that prevents a trustworthy verdict raises UnauditedError.
Nothing in this module ever downgrades UNAUDITED to a pass.
"""

import json
import re
import urllib.error
import urllib.request

SCHEMA_VERSION = 1

VERDICT_KEYS = {"attack", "mechanism_class", "offending_element", "confidence", "rationale"}


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
    """Strict schema validation. Any deviation is UNAUDITED, never coerced.

    Semantics: attack=true requires a non-empty closed-list mechanism_class
    and a named offending_element; attack=false requires both to be "".
    """
    if set(obj.keys()) != VERDICT_KEYS:
        raise UnauditedError(f"verdict keys mismatch: {sorted(obj.keys())}")
    if not isinstance(obj["attack"], bool):
        raise UnauditedError("attack must be bool")
    if not isinstance(obj["offending_element"], str):
        raise UnauditedError("offending_element must be string")
    if not isinstance(obj["rationale"], str):
        raise UnauditedError("rationale must be string")
    if not isinstance(obj["confidence"], (int, float)) or isinstance(obj["confidence"], bool):
        raise UnauditedError("confidence must be number")
    if not 0.0 <= obj["confidence"] <= 1.0:
        raise UnauditedError("confidence out of range")
    if obj["attack"]:
        if obj["mechanism_class"] not in mechanism_classes:
            raise UnauditedError(f"mechanism_class not in closed list: {obj['mechanism_class']!r}")
        if not obj["offending_element"]:
            raise UnauditedError("attack=true requires a named offending_element")
    else:
        if obj["mechanism_class"] != "" or obj["offending_element"] != "":
            raise UnauditedError("attack=false requires empty mechanism_class and offending_element")
    return obj
