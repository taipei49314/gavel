"""Approved-models manifest: pin comparison is the enforceable half of pinning."""

import json

import pytest
from gavel.judge import UnauditedError, check_approved

APPROVED = {
    "schema_version": 1,
    "approved": [
        {"model": "qwen3.5:35b-a3b",
         "manifest_digest": "3460ffeede5453ead027dbd2f821b12ad0aa3de54630971993babdb2165221f7",
         "role": "gating", "transport": "ollama"},
        {"model": "gemini-4-argon-high", "manifest_digest": None,
         "role": "recorded-informed", "transport": "agy"},
    ],
}


@pytest.fixture
def approved_path(tmp_path):
    p = tmp_path / "approved-models.json"
    p.write_text(json.dumps(APPROVED), encoding="utf-8")
    return p


def test_matching_digest_passes(approved_path):
    pin = {"model": "qwen3.5:35b-a3b", "manifest_digest": APPROVED["approved"][0]["manifest_digest"]}
    check_approved(pin, approved_path)


def test_wrong_digest_refused(approved_path):
    pin = {"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:DIFFERENT"}
    with pytest.raises(UnauditedError, match="not in approved manifest"):
        check_approved(pin, approved_path)


def test_unknown_model_refused(approved_path):
    pin = {"model": "qwen3.5:27b", "manifest_digest": "sha256:whatever"}
    with pytest.raises(UnauditedError):
        check_approved(pin, approved_path)


def test_cloud_arm_matches_on_model_id_and_transport(approved_path):
    pin = {"model": "gemini-4-argon-high", "manifest_digest": None}
    check_approved(pin, approved_path, transport="agy")


def test_cloud_arm_wrong_transport_refused(approved_path):
    pin = {"model": "gemini-4-argon-high", "manifest_digest": None}
    with pytest.raises(UnauditedError):
        check_approved(pin, approved_path, transport="ollama")
