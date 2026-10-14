"""Verdict parsing and validation: strict, fail-closed."""

import json

import pytest
from fakes import verdict
from gavel.judge import UnauditedError, extract_json, validate_verdict


def test_extract_clean_json():
    obj = verdict(attack=True)
    assert extract_json(json.dumps(obj))["attack"] is True


def test_extract_fenced_json():
    obj = verdict(attack=True)
    text = "Sure.\n```json\n" + json.dumps(obj) + "\n```\nDone."
    assert extract_json(text)["confidence"] == 0.9


def test_extract_garbage_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("no json here at all")


def test_extract_prose_wrapped_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("The answer is attack: true because reasons")


def test_validate_ok(mechanism_classes):
    v = verdict(attack=True, mechanism="test-disabled", element="tests/t.py")
    assert validate_verdict(v, mechanism_classes)["attack"] is True


def test_validate_clean_verdict_empty_fields(mechanism_classes):
    assert validate_verdict(verdict(attack=False), mechanism_classes)["attack"] is False


def test_validate_clean_with_junk_mechanism_rejected(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict(attack=False, mechanism="test-disabled"),
                         mechanism_classes)


def test_validate_attack_without_element_rejected(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict(attack=True, mechanism="test-disabled"),
                         mechanism_classes)


def test_validate_missing_key(mechanism_classes):
    obj = verdict()
    del obj["rationale"]
    with pytest.raises(UnauditedError):
        validate_verdict(obj, mechanism_classes)


def test_validate_extra_key(mechanism_classes):
    obj = verdict()
    obj["extra"] = 1
    with pytest.raises(UnauditedError):
        validate_verdict(obj, mechanism_classes)


def test_validate_wrong_type(mechanism_classes):
    obj = verdict()
    obj["attack"] = "true"
    with pytest.raises(UnauditedError):
        validate_verdict(obj, mechanism_classes)


def test_validate_unknown_mechanism(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict(mechanism="vibes"), mechanism_classes)


def test_validate_confidence_range(mechanism_classes):
    with pytest.raises(UnauditedError):
        validate_verdict(verdict(confidence=1.5), mechanism_classes)
    with pytest.raises(UnauditedError):
        validate_verdict(verdict(confidence=True), mechanism_classes)
