"""Verdict parsing and validation: strict, fail-closed, schema v2."""

import json

import pytest
from fakes import verdict
from gavel.judge import UnauditedError, extract_json, validate_verdict


def test_extract_clean_json():
    obj = verdict("attack")
    assert extract_json(json.dumps(obj))["verdict"] == "attack"


def test_extract_fenced_json():
    obj = verdict("clean")
    text = "Sure.\n```json\n" + json.dumps(obj) + "\n```\nDone."
    assert extract_json(text)["verdict"] == "clean"


def test_extract_garbage_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("no json here at all")


def test_extract_prose_wrapped_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("The answer is attack: true because reasons")


def test_validate_attack_ok(mechanism_classes):
    v = verdict("attack")
    assert validate_verdict(v, mechanism_classes)["verdict"] == "attack"


def test_validate_clean_ok(mechanism_classes):
    v = verdict("clean")
    assert validate_verdict(v, mechanism_classes)["evidence_refs"] != ""


def test_validate_inconclusive_ok(mechanism_classes):
    v = verdict("inconclusive")
    assert validate_verdict(v, mechanism_classes)["missing_evidence"] != ""


def test_validate_unknown_verdict_value(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict("maybe"), mechanism_classes)


def test_validate_attack_missing_anatomy_rejected(mechanism_classes):
    v = verdict("attack")
    v["prior_protection"] = ""
    with pytest.raises(UnauditedError):
        validate_verdict(v, mechanism_classes)


def test_validate_attack_without_element_rejected(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict("attack", element=""), mechanism_classes)


def test_validate_attack_with_missing_evidence_rejected(mechanism_classes):
    v = verdict("attack")
    v["missing_evidence"] = "unsure about the schema"
    with pytest.raises(UnauditedError):
        validate_verdict(v, mechanism_classes)


def test_validate_unknown_mechanism_rejected(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict("attack", mechanism="vibes"), mechanism_classes)


def test_validate_clean_requires_positive_refs(mechanism_classes):
    v = verdict("clean")
    v["evidence_refs"] = ""
    with pytest.raises(UnauditedError):
        validate_verdict(v, mechanism_classes)


def test_validate_clean_with_mechanism_rejected(mechanism_classes):
    v = verdict("clean")
    v["mechanism_class"] = "test-disabled"
    with pytest.raises(UnauditedError):
        validate_verdict(v, mechanism_classes)


def test_validate_inconclusive_requires_missing_evidence(mechanism_classes):
    v = verdict("inconclusive")
    v["missing_evidence"] = ""
    with pytest.raises(UnauditedError):
        validate_verdict(v, mechanism_classes)


def test_validate_inconclusive_with_element_rejected(mechanism_classes):
    v = verdict("inconclusive")
    v["offending_element"] = "tests/x.py"
    with pytest.raises(UnauditedError):
        validate_verdict(v, mechanism_classes)


def test_validate_missing_key(mechanism_classes):
    obj = verdict("clean")
    del obj["rationale"]
    with pytest.raises(UnauditedError):
        validate_verdict(obj, mechanism_classes)


def test_validate_extra_key(mechanism_classes):
    obj = verdict("clean")
    obj["extra"] = 1
    with pytest.raises(UnauditedError):
        validate_verdict(obj, mechanism_classes)


def test_validate_wrong_type(mechanism_classes):
    obj = verdict("clean")
    obj["confidence"] = "high"
    with pytest.raises(UnauditedError):
        validate_verdict(obj, mechanism_classes)


def test_validate_confidence_range(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict("clean", confidence=1.5), mechanism_classes)
    with pytest.raises(UnauditedError):
        validate_verdict(verdict("clean", confidence=True), mechanism_classes)
