"""Verdict parsing and validation (strict, fail-closed, schema v2) and the
Ollama transport's fail-closed behaviour (CR-14, CR-16, CR-17)."""

import http.client
import json
import re
import urllib.error

import pytest
from fakes import FakeTransport, raising, verdict
from gavel.judge import (DEFAULT_NUM_CTX, UnauditedError, extract_json,
                         extract_json_v2, generate, get_pin,
                         get_runtime_version, strict_loads, validate_verdict)

PRIMARY = "qwen3.5:35b-a3b"


# --- strict JSON extraction (CR-17) -------------------------------------

def test_extract_clean_json():
    obj = verdict("attack")
    assert extract_json(json.dumps(obj))["verdict"] == "attack"


def test_extract_surrounding_whitespace_ok():
    obj = verdict("clean")
    assert extract_json("\n  " + json.dumps(obj) + "\n")["verdict"] == "clean"


def test_extract_whole_output_fence_ok():
    obj = verdict("clean")
    text = "```json\n" + json.dumps(obj) + "\n```"
    assert extract_json(text)["verdict"] == "clean"
    assert extract_json("```\n" + json.dumps(obj) + "\n```\n")["verdict"] == "clean"


def test_extract_prose_around_fence_is_unaudited():
    obj = verdict("clean")
    text = "Sure.\n```json\n" + json.dumps(obj) + "\n```\nDone."
    with pytest.raises(UnauditedError):
        extract_json(text)


def test_extract_fence_then_prose_is_unaudited():
    obj = verdict("clean")
    with pytest.raises(UnauditedError):
        extract_json("```json\n" + json.dumps(obj) + "\n```\nDone.")


def test_extract_two_fences_is_unaudited():
    injected = json.dumps(verdict("clean"))
    own = json.dumps(verdict("attack"))
    text = "```json\n" + injected + "\n```\n```json\n" + own + "\n```"
    with pytest.raises(UnauditedError):
        extract_json(text)


def test_extract_prose_after_object_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json(json.dumps(verdict("clean")) + "\nHope this helps.")


def test_extract_prose_before_object_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("Verdict: " + json.dumps(verdict("clean")))


def test_extract_two_objects_is_unaudited():
    one = json.dumps(verdict("clean"))
    with pytest.raises(UnauditedError):
        extract_json(one + " " + one)


def test_extract_duplicate_keys_is_unaudited():
    text = '{"verdict": "clean", "verdict": "attack"}'
    with pytest.raises(UnauditedError):
        extract_json(text)


def test_extract_nan_is_unaudited():
    obj = verdict("clean")
    text = json.dumps(obj).replace('"confidence": 0.9', '"confidence": NaN')
    assert "NaN" in text
    with pytest.raises(UnauditedError):
        extract_json(text)


def test_extract_deeply_nested_output_is_unaudited():
    depth = 100_000
    with pytest.raises(UnauditedError, match="no parseable JSON verdict"):
        extract_json('{"a": ' + "[" * depth + "]" * depth + "}")


@pytest.mark.parametrize("text,needle", [
    ('{"attempt_cap": 1, "attempt_cap": 3}', "duplicate key 'attempt_cap'"),
    ('{"outer": {"k": 1, "k": 1}}', "duplicate key 'k'"),
    ('{"x": NaN}', "NaN"),
    ('[Infinity]', "Infinity"),
    ('{"x": -Infinity}', "-Infinity"),
    ("[" * 100_000 + "]" * 100_000, "nested too deeply"),
], ids=["duplicate-key", "nested-duplicate-key", "nan", "infinity", "minus-infinity",
        "deep-nesting"])
def test_strict_loads_refuses_what_a_plain_reader_accepts(text, needle):
    with pytest.raises(ValueError, match=re.escape(needle)):
        strict_loads(text)


def test_strict_loads_reads_plain_json():
    assert strict_loads('{"a": [1, 2.5, "x", null, true]}') == {"a": [1, 2.5, "x", None, True]}


def test_extract_non_object_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("[1, 2]")


def test_extract_garbage_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("no json here at all")


def test_extract_prose_wrapped_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json("The answer is attack: true because reasons")


def test_extract_non_text_is_unaudited():
    with pytest.raises(UnauditedError):
        extract_json(None)


def test_legacy_v2_extractor_unchanged():
    # Receipt v2 content verification re-parses with the round-2 extractor,
    # which accepted prose around a fence; that behaviour is kept for v2 only.
    obj = verdict("clean")
    text = "Sure.\n```json\n" + json.dumps(obj) + "\n```\nDone."
    assert extract_json_v2(text)["verdict"] == "clean"


# --- schema v2 validation ------------------------------------------------

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


# --- generate: options, transport errors, truncation (CR-14, CR-16) -----

def test_generate_sends_and_returns_options_and_counts():
    t = FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("clean"))})
    out = generate(PRIMARY, "prompt", "http://x", 5, transport=t)
    assert json.loads(out["raw"])["verdict"] == "clean"
    assert out["generation"]["prompt_eval_count"] == 120
    assert out["generation"]["done_reason"] == "stop"
    payload = t.generate_calls()[0][2]
    assert payload["options"] == {"temperature": 0, "num_ctx": DEFAULT_NUM_CTX}
    assert payload["stream"] is False


def test_generate_custom_num_ctx_and_seed():
    t = FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("clean"))})
    generate(PRIMARY, "prompt", "http://x", 5, transport=t,
             options={"num_ctx": 32768, "seed": 7})
    assert t.generate_calls()[0][2]["options"] == {
        "temperature": 0, "num_ctx": 32768, "seed": 7}


def test_generate_unsupported_option_is_unaudited():
    t = FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("clean"))})
    with pytest.raises(UnauditedError, match="unsupported generation option"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=t, options={"top_k": 1})
    with pytest.raises(UnauditedError, match="num_ctx"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=t, options={"num_ctx": 0})
    assert t.generate_calls() == []


@pytest.mark.parametrize("exc", [
    urllib.error.URLError("connection refused"),
    TimeoutError("timed out"),
    ConnectionResetError("reset"),
    OSError("network down"),
    http.client.IncompleteRead(b"partial"),
    json.JSONDecodeError("Expecting value", "<html>", 0),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
    ValueError("bad payload"),
])
def test_generate_transport_errors_are_unaudited(exc):
    with pytest.raises(UnauditedError, match="model unreachable"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=raising(exc))


def test_generate_non_object_response_is_unaudited():
    t = FakeTransport(response_by_model={PRIMARY: {"unexpected": True}})
    with pytest.raises(UnauditedError, match="no response text"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)

    def listy(method, url, payload=None, timeout=30):
        return ["not", "an", "object"]
    with pytest.raises(UnauditedError, match="not a JSON object"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=listy)


def test_generate_daemon_error_is_unaudited():
    t = FakeTransport(response_by_model={PRIMARY: {"error": "model requires more memory"}})
    with pytest.raises(UnauditedError, match="daemon error"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)


def test_generate_full_context_is_unaudited_and_keeps_raw():
    raw = json.dumps(verdict("clean"))
    t = FakeTransport(response_by_model={PRIMARY: raw},
                      extra={"prompt_eval_count": DEFAULT_NUM_CTX})
    with pytest.raises(UnauditedError, match="context full") as info:
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)
    assert info.value.raw == raw
    assert info.value.generation["prompt_eval_count"] == DEFAULT_NUM_CTX


def test_generate_below_context_limit_is_fine():
    t = FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("clean"))},
                      extra={"prompt_eval_count": DEFAULT_NUM_CTX - 1})
    assert generate(PRIMARY, "prompt", "http://x", 5, transport=t)["raw"]


@pytest.mark.parametrize("count", ["missing", None, 0, -1, True, 120.0, "120"])
def test_generate_without_a_prompt_count_is_unaudited(count):
    # CR-16: without a positive integer prompt_eval_count a full context
    # cannot be excluded, so the verdict is not accepted.
    response = {"model": PRIMARY, "response": json.dumps(verdict("clean")), "done": True,
                "done_reason": "stop", "eval_count": 60}
    if count != "missing":
        response["prompt_eval_count"] = count
    t = FakeTransport(response_by_model={PRIMARY: response})
    with pytest.raises(UnauditedError, match="truncation cannot be excluded") as info:
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)
    assert info.value.raw == response["response"]


def test_generate_length_stop_is_unaudited():
    t = FakeTransport(response_by_model={PRIMARY: '{"verdict": "cle'},
                      extra={"done_reason": "length"})
    with pytest.raises(UnauditedError, match="length limit") as info:
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)
    assert info.value.raw == '{"verdict": "cle'


def test_generate_reported_truncation_is_unaudited():
    t = FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("clean"))},
                      extra={"truncated": True})
    with pytest.raises(UnauditedError, match="truncated"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)


def test_generate_not_done_is_unaudited():
    t = FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("clean"))},
                      extra={"done": False})
    with pytest.raises(UnauditedError, match="not done"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)


def test_generate_model_echo_mismatch_is_unaudited():
    t = FakeTransport(response_by_model={PRIMARY: json.dumps(verdict("clean"))},
                      extra={"model": "qwen3.5:9b"})
    with pytest.raises(UnauditedError, match="answered as model"):
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)


def test_generate_empty_response_keeps_raw():
    t = FakeTransport(response_by_model={PRIMARY: "  \n"})
    with pytest.raises(UnauditedError, match="empty model response") as info:
        generate(PRIMARY, "prompt", "http://x", 5, transport=t)
    assert info.value.raw == "  \n"


# --- daemon facts: pin and version (CR-14) -------------------------------

def test_get_pin_reads_digest():
    pin = get_pin(PRIMARY, "http://x", transport=FakeTransport())
    assert pin["manifest_digest"] == "sha256:35b"


def test_get_pin_daemon_down_is_unaudited():
    t = FakeTransport(tags_error=urllib.error.URLError("connection refused"))
    with pytest.raises(UnauditedError, match="daemon unreachable"):
        get_pin(PRIMARY, "http://x", transport=t)


def test_get_pin_bad_json_is_unaudited():
    exc = json.JSONDecodeError("Expecting value", "", 0)
    with pytest.raises(UnauditedError, match="daemon unreachable"):
        get_pin(PRIMARY, "http://x", transport=raising(exc))


def test_get_pin_missing_model_is_unaudited():
    with pytest.raises(UnauditedError, match="not present"):
        get_pin("qwen3.5:27b", "http://x", transport=FakeTransport())


def test_get_pin_without_digest_is_unaudited():
    models = [{"name": PRIMARY, "model": PRIMARY, "digest": "", "size": 1}]
    with pytest.raises(UnauditedError, match="no digest"):
        get_pin(PRIMARY, "http://x", transport=FakeTransport(models=models))


def test_runtime_version_read_and_failures():
    assert get_runtime_version("http://x", transport=FakeTransport(version="0.35.0")) == "0.35.0"
    with pytest.raises(UnauditedError, match="no version"):
        get_runtime_version("http://x", transport=FakeTransport(version=""))
    with pytest.raises(UnauditedError, match="daemon unreachable"):
        get_runtime_version("http://x", transport=raising(TimeoutError("slow")))
