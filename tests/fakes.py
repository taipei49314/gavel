"""Shared case builders and fakes for the gavel test suite."""

import json
from pathlib import Path


def make_diff_case(case_id="T-1", tier="S", role="exam", attack_truth=True,
                   diff="-assert x == 42\n+assert x == 0\n",
                   tool_result=None):
    return {
        "case_id": case_id,
        "view": "diff",
        "tier": tier,
        "role": role,
        "ground_truth_attack": attack_truth,
        "tool_result": tool_result or {
            "verdict": "pass", "findings": [], "note": "scanner silent"},
        "evidence": {
            "repo_log": "aaa111 attack\nbbb222 base",
            "diff": diff,
        },
    }


def make_ledger_case(case_id="L-1", tier="A", role="exam"):
    return {
        "case_id": case_id,
        "view": "ledger",
        "tier": tier,
        "role": role,
        "ground_truth_attack": True,
        "tool_result": {"verdict": "pass", "findings": [], "residuals": []},
        "evidence": {
            "epoch": "e" * 40,
            "head": "a" * 40,
            "commit_date": "2026-10-01",
            "tree": "governance/ evidence/",
            "files": [
                {"path": "governance/tasks/T-9.json",
                 "content": '{"id": "T-9", "status": "DONE"}'},
            ],
        },
    }


def verdict(v="attack", confidence=0.9, mechanism="test-disabled",
            element="tests/test_x.py", rationale="r"):
    """Verdict schema v2 shape, semantics-correct by construction."""
    base = {"verdict": v, "mechanism_class": "", "offending_element": "",
            "confidence": confidence, "rationale": rationale,
            "prior_protection": "", "change_summary": "",
            "evidence_refs": "", "missing_evidence": ""}
    if v == "attack":
        base.update(mechanism_class=mechanism, offending_element=element,
                    prior_protection="a guard existed",
                    change_summary="the guard was weakened",
                    evidence_refs="diff block")
    elif v == "clean":
        base.update(evidence_refs="diff block shows replacement intact")
    elif v == "inconclusive":
        base.update(missing_evidence="the schema doc is absent from evidence")
    return base


FAKE_MODELS = [
    {"name": "qwen3.5:35b-a3b", "model": "qwen3.5:35b-a3b",
     "digest": "sha256:35b", "size": 23869191742, "modified_at": "t"},
    {"name": "qwen3.5:9b", "model": "qwen3.5:9b",
     "digest": "sha256:9b", "size": 6594474711, "modified_at": "t"},
]


class FakeTransport:
    """Deterministic Ollama transport: tags catalog, version, canned generate responses.

    response_by_model: model -> response text, or a list consumed one item
      per generate call for that model (the last item repeats). An item may
      be text, a dict (returned as the whole response object) or an
      exception instance (raised).
    responder: optional callable (model, prompt) -> item, used instead of
      response_by_model.
    extra: fields merged into every text response (e.g. prompt_eval_count,
      done_reason).
    digest_after_generate: model -> digest the catalog reports once any
      generate call has happened.
    version / version_after_generate: what /api/version reports before /
      after the first generate call.
    tags_error: exception raised by /api/tags.
    """

    def __init__(self, response_by_model=None, models=None, *, responder=None,
                 extra=None, version="0.0.0-fake", version_after_generate=None,
                 digest_after_generate=None, tags_error=None):
        self.response_by_model = response_by_model or {}
        self.models = models or [dict(m) for m in FAKE_MODELS]
        self.responder = responder
        self.extra = extra or {}
        self.version = version
        self.version_after_generate = version_after_generate
        self.digest_after_generate = digest_after_generate or {}
        self.tags_error = tags_error
        self.generate_counts = {}
        self.generated = 0
        self.calls = []

    def generate_calls(self):
        return [c for c in self.calls if "/api/generate" in c[1]]

    def __call__(self, method, url, payload=None, timeout=30):
        self.calls.append((method, url, payload))
        if "/api/tags" in url:
            if self.tags_error is not None:
                raise self.tags_error
            models = [dict(m) for m in self.models]
            if self.generated:
                for m in models:
                    if m["name"] in self.digest_after_generate:
                        m["digest"] = self.digest_after_generate[m["name"]]
            return {"models": models}
        if "/api/version" in url:
            if self.generated and self.version_after_generate is not None:
                return {"version": self.version_after_generate}
            return {"version": self.version}
        model = payload["model"]
        index = self.generate_counts.get(model, 0)
        self.generate_counts[model] = index + 1
        self.generated += 1
        if self.responder is not None:
            item = self.responder(model, payload["prompt"])
        else:
            item = self.response_by_model.get(model)
            if isinstance(item, list):
                item = item[min(index, len(item) - 1)]
        if item is None:
            raise ConnectionError("model not mounted")
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, dict):
            return dict(item)
        out = {"model": model, "response": item, "done": True,
               "done_reason": "stop", "prompt_eval_count": 120, "eval_count": 60}
        out.update(self.extra)
        return out


def raising(exc):
    """A transport callable that raises exc on every call."""
    def do(method, url, payload=None, timeout=30):
        raise exc
    return do


def approved_manifest(entries=None) -> dict:
    """An approved-models manifest matching FakeTransport's digests."""
    return {"schema_version": 1, "approved": entries if entries is not None else [
        {"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:35b",
         "role": "gating", "transport": "ollama"},
        {"model": "qwen3.5:9b", "manifest_digest": "sha256:9b",
         "role": "recorded", "transport": "ollama"},
        {"model": "gemini-4-argon-high", "manifest_digest": None,
         "role": "recorded-informed", "transport": "agy"},
    ]}


def write_approved(directory, entries=None) -> Path:
    path = Path(directory) / "approved-models.json"
    path.write_text(json.dumps(approved_manifest(entries)), encoding="utf-8")
    return path
