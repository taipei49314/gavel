"""Shared case builders and fakes for the gavel test suite."""

import json


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


class FakeTransport:
    """Deterministic transport: tags catalog + canned generate responses."""

    def __init__(self, response_by_model=None, models=None):
        self.response_by_model = response_by_model or {}
        self.models = models or [
            {"name": "qwen3.5:35b-a3b", "model": "qwen3.5:35b-a3b",
             "digest": "sha256:35b", "size": 23869191742, "modified_at": "t"},
            {"name": "qwen3.5:9b", "model": "qwen3.5:9b",
             "digest": "sha256:9b", "size": 6594474711, "modified_at": "t"},
        ]
        self.calls = []

    def __call__(self, method, url, payload=None, timeout=30):
        self.calls.append((method, url, payload))
        if "/api/tags" in url:
            return {"models": self.models}
        model = payload["model"]
        resp = self.response_by_model.get(model)
        if resp is None:
            raise ConnectionError("model not mounted")
        return {"response": resp}
