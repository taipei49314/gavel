"""Approved-models manifest: pin comparison is the enforceable half of pinning.

Covers CR-02 (default path is the repo root, not the working directory;
missing or unparseable manifest is UNAUDITED) and CR-15 (a null digest
approves only an explicitly declared cloud transport).
"""

import hashlib
import json
from pathlib import Path

import gavel
import pytest
from gavel.judge import (UnauditedError, approved_model_entry, check_approved,
                         default_approved_path, load_approved)

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

REPO_ROOT = Path(gavel.__file__).resolve().parent.parent


def write(tmp_path, data, name="approved-models.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return p


@pytest.fixture
def approved_path(tmp_path):
    return write(tmp_path, APPROVED)


def test_matching_digest_passes(approved_path):
    pin = {"model": "qwen3.5:35b-a3b", "manifest_digest": APPROVED["approved"][0]["manifest_digest"]}
    check_approved(pin, approved_path)


def test_check_returns_the_identity_of_the_approving_file(approved_path):
    # Receipts and results.json record which file gated the judgment.
    pin = {"model": "qwen3.5:35b-a3b", "manifest_digest": APPROVED["approved"][0]["manifest_digest"]}
    assert check_approved(pin, approved_path) == {
        "file": "approved-models.json",
        "sha256": hashlib.sha256(approved_path.read_bytes()).hexdigest()}
    cloud = {"model": "gemini-4-argon-high", "manifest_digest": None}
    assert check_approved(cloud, approved_path, transport="agy")["file"] == "approved-models.json"


def test_duplicate_keys_in_the_manifest_are_unaudited(tmp_path):
    # A plain reader keeps the last "approved" list; two readers could see
    # different approvals.
    path = write(tmp_path, '{"approved": [], "approved": [{"model": "qwen3.5:35b-a3b", '
                           '"manifest_digest": "x", "transport": "ollama"}]}')
    with pytest.raises(UnauditedError, match="not valid JSON"):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": "x"}, path)


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


def test_local_digest_entry_refused_for_other_transport(approved_path):
    pin = {"model": "qwen3.5:35b-a3b",
           "manifest_digest": APPROVED["approved"][0]["manifest_digest"]}
    with pytest.raises(UnauditedError):
        check_approved(pin, approved_path, transport="agy")


# --- CR-15: null digest only for an explicitly declared cloud transport ---

def test_null_digest_without_transport_approves_nothing(tmp_path):
    path = write(tmp_path, {"approved": [
        {"model": "qwen3.5:35b-a3b", "manifest_digest": None}]})
    with pytest.raises(UnauditedError):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:any"}, path)
    with pytest.raises(UnauditedError):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": None}, path)


def test_missing_digest_key_approves_nothing(tmp_path):
    path = write(tmp_path, {"approved": [{"model": "qwen3.5:35b-a3b", "transport": "ollama"}]})
    with pytest.raises(UnauditedError):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:any"}, path)


def test_null_digest_with_local_transport_approves_nothing(tmp_path):
    path = write(tmp_path, {"approved": [
        {"model": "qwen3.5:35b-a3b", "manifest_digest": None, "transport": "ollama"}]})
    with pytest.raises(UnauditedError):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:any"}, path)


def test_cloud_entry_does_not_approve_a_pin_with_a_digest(approved_path):
    pin = {"model": "gemini-4-argon-high", "manifest_digest": "sha256:local-copy"}
    with pytest.raises(UnauditedError):
        check_approved(pin, approved_path, transport="agy")


def test_empty_digest_entry_approves_nothing(tmp_path):
    path = write(tmp_path, {"approved": [
        {"model": "qwen3.5:35b-a3b", "manifest_digest": "", "transport": "ollama"}]})
    with pytest.raises(UnauditedError):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": ""}, path)


# --- CR-02: manifest location and readability ------------------------------

def test_missing_manifest_is_unaudited(tmp_path):
    with pytest.raises(UnauditedError, match="unreadable"):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": "x"},
                       tmp_path / "absent.json")


def test_unparseable_manifest_is_unaudited(tmp_path):
    path = write(tmp_path, "{not json")
    with pytest.raises(UnauditedError, match="not valid JSON"):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": "x"}, path)


def test_malformed_manifest_is_unaudited(tmp_path):
    for data in ({"approved": "everything"}, ["not", "an", "object"], {}):
        path = write(tmp_path, data)
        with pytest.raises(UnauditedError, match="malformed"):
            load_approved(path)


def test_unaudited_reason_names_file_not_directory(tmp_path):
    with pytest.raises(UnauditedError) as info:
        load_approved(tmp_path / "absent.json")
    assert str(tmp_path) not in info.value.reason
    assert "absent.json" in info.value.reason


def test_default_path_is_repo_root_not_cwd(tmp_path, monkeypatch):
    # A permissive approved-models.json in the working directory must not
    # be picked up: the default resolves from the package location.
    write(tmp_path, {"approved": [
        {"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:cwd-only",
         "transport": "ollama"}]})
    monkeypatch.chdir(tmp_path)
    assert default_approved_path() == REPO_ROOT / "approved-models.json"
    with pytest.raises(UnauditedError):
        check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": "sha256:cwd-only"})
    committed = json.loads((REPO_ROOT / "approved-models.json").read_text(encoding="utf-8"))
    digest = next(e["manifest_digest"] for e in committed["approved"]
                  if e["model"] == "qwen3.5:35b-a3b")
    check_approved({"model": "qwen3.5:35b-a3b", "manifest_digest": digest})


def test_approved_model_entry_uses_same_loader(approved_path, tmp_path):
    assert approved_model_entry("gemini-4-argon-high", approved_path)["transport"] == "agy"
    assert approved_model_entry("nope", approved_path) is None
    with pytest.raises(UnauditedError):
        approved_model_entry("qwen3.5:35b-a3b", tmp_path / "absent.json")
