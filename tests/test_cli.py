"""The command line: scan exit codes (CR-05, SPEC §5/§6), the exam / evaluate /
verify / pin wiring, and fail-closed errors (CR-14).

The Ollama daemon is replaced by FakeTransport (gavel.judge._request_json)
and the agy transport by a fake generate function (gavel.qualify.agy_generate);
no model is called.
"""

import itertools
import json

import pytest
from fakes import (FakeTransport, NEGATIVE_BAR, legacy_receipt, load_json,
                   make_diff_case, marked_case, marker, raising, verdict,
                   write_approved, write_lines, write_paper)
from gavel import cli, judge, qualify
from gavel.cli import EXAM_EXIT, SCAN_REQUIRED_ARMS, main, scan_exit_code
from gavel.prompt import MECHANISM_CLASSES
from gavel.receipts import verify_file

PRIMARY = "qwen3.5:35b-a3b"
FAST = "qwen3.5:9b"
INFORMED = "gemini-4-argon-high"
UNAUDITED = None
VALUES = ["attack", "clean", "inconclusive", UNAUDITED]


def outcome(value):
    if value is UNAUDITED:
        return {"verdict": None, "unaudited": "empty model response"}
    return {"verdict": verdict(value), "unaudited": None}


# --- the scan exit-code matrix (CR-05) ---------------------------------------------

def expected_code(*values):
    if UNAUDITED in values:
        return 2
    return 0 if all(v == "clean" for v in values) else 1


@pytest.mark.parametrize("primary,fast", list(itertools.product(VALUES, VALUES)))
def test_scan_exit_matrix_required_arms(primary, fast):
    code, reasons = scan_exit_code({"primary": outcome(primary), "fast": outcome(fast)})
    assert code == expected_code(primary, fast), reasons
    if code == 1 and primary != fast:
        assert any(r.startswith("arms disagree") for r in reasons)
    if "inconclusive" in (primary, fast) and code == 1:
        assert any(r.startswith("inconclusive") for r in reasons)


@pytest.mark.parametrize("primary,fast,informed", list(itertools.product(VALUES, VALUES, VALUES)))
def test_scan_exit_matrix_with_opt_in_informed(primary, fast, informed):
    # An opt-in arm can only make the result stricter: its UNAUDITED is 2,
    # its attack or inconclusive (or any disagreement) is 1, never 0.
    code, _ = scan_exit_code({"primary": outcome(primary), "fast": outcome(fast),
                              "informed": outcome(informed)})
    assert code == expected_code(primary, fast, informed)


def test_inconclusive_is_never_clean():
    for pair in (("inconclusive", "inconclusive"), ("clean", "inconclusive"),
                 ("inconclusive", "clean")):
        assert scan_exit_code({"primary": outcome(pair[0]), "fast": outcome(pair[1])})[0] == 1


def test_missing_required_arm_is_unaudited():
    code, reasons = scan_exit_code({"primary": outcome("clean")})
    assert code == 2 and "required arm(s) not run: fast" in reasons
    code, _ = scan_exit_code({"primary": outcome("attack")})
    assert code == 2  # UNAUDITED wins over the finding
    assert SCAN_REQUIRED_ARMS == ("primary", "fast")


def test_malformed_outcome_is_unaudited():
    bad = {"verdict": {"rationale": "no verdict field"}, "unaudited": None}
    assert scan_exit_code({"primary": bad, "fast": outcome("clean")})[0] == 2
    both = {"verdict": verdict("clean"), "unaudited": "schema"}
    assert scan_exit_code({"primary": both, "fast": outcome("clean")})[0] == 2


# --- scan end to end -------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    """Case file, approved-models file, receipts path and a daemon installer."""
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(make_diff_case()), encoding="utf-8")
    approved = write_approved(tmp_path)
    receipts = tmp_path / "out" / "scan.jsonl"

    def daemon(primary="clean", fast="clean", **kw):
        responses = {}
        for model, value in ((PRIMARY, primary), (FAST, fast)):
            responses[model] = "" if value is UNAUDITED else json.dumps(verdict(value))
        t = FakeTransport(response_by_model=responses, **kw)
        monkeypatch.setattr(judge, "_request_json", t)
        return t

    return {"case": case_path, "approved": approved, "receipts": receipts, "daemon": daemon}


def scan(env, *extra):
    return main(["scan", str(env["case"]), "--approved-models", str(env["approved"]),
                 "--receipts", str(env["receipts"]), "--base-url", "http://x",
                 "--timeout", "5", *extra])


@pytest.mark.parametrize("primary,fast", list(itertools.product(VALUES, VALUES)))
def test_scan_command_exit_matrix(env, capsys, primary, fast):
    env["daemon"](primary, fast)
    code = scan(env)
    assert code == expected_code(primary, fast)
    assert capsys.readouterr().out.splitlines()[-1].startswith(f"exit {code}: ")
    receipts = verify_file(env["receipts"], MECHANISM_CLASSES, content=True)
    assert [r["arm"] for r in receipts] == ["primary", "fast"]
    assert all(r["paper_id"] is None and r["attempt"] == 1 for r in receipts)


def test_scan_informed_arm_goes_to_agy_not_ollama(env, monkeypatch):
    t = env["daemon"]()
    calls = []

    def fake_agy(model, prompt, base_url, timeout_s, transport=None, options=None):
        calls.append((model, options))
        return {"raw": json.dumps(verdict("clean")), "generation": {"exit_code": 0},
                "transport_version": {"executable_sha256": "e" * 64}}
    monkeypatch.setattr(qualify, "agy_generate", fake_agy)
    assert scan(env, "--arms", "primary", "fast", "informed") == 0
    assert calls == [(INFORMED, None)]
    assert all(c[2]["model"] != INFORMED for c in t.generate_calls())
    informed = verify_file(env["receipts"], MECHANISM_CLASSES, content=True)[-1]
    assert informed["arm"] == "informed" and informed["transport"]["name"] == "agy"
    assert informed["execution"] == {"timeout_s": 5.0} and informed["options"] == {}


def test_scan_informed_attack_is_a_finding(env, monkeypatch):
    env["daemon"]()
    monkeypatch.setattr(qualify, "agy_generate", lambda *a, **k: {
        "raw": json.dumps(verdict("attack")), "generation": {}})
    assert scan(env, "--arms", "primary", "fast", "informed") == 1


def test_scan_without_a_required_arm_is_refused_before_judging(env, capsys):
    t = env["daemon"]()
    assert scan(env, "--arms", "primary") == 2
    assert "not selected: fast" in capsys.readouterr().err
    assert t.calls == [] and not env["receipts"].exists()


def test_scan_refuses_a_legacy_receipts_file_before_judging(env, capsys):
    t = env["daemon"]()
    env["receipts"].parent.mkdir(parents=True)
    write_lines(env["receipts"], [legacy_receipt(version=2)])
    assert scan(env) == 2
    assert "new file" in capsys.readouterr().err
    assert t.calls == []


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", json.dumps({"view": "diff"}),
                                     json.dumps({**make_diff_case(), "view": "voodoo"})])
def test_scan_bad_case_file_is_unaudited(env, capsys, content):
    t = env["daemon"]()
    env["case"].write_text(content, encoding="utf-8")
    assert scan(env) == 2
    assert "cannot be used" in capsys.readouterr().err
    assert t.calls == []


def test_scan_missing_case_file_is_unaudited(env, tmp_path):
    env["daemon"]()
    env["case"] = tmp_path / "absent.json"
    assert scan(env) == 2


def test_scan_missing_approved_models_file_is_unaudited(env, tmp_path, capsys):
    t = env["daemon"]()
    env["approved"] = tmp_path / "absent-approved.json"
    assert scan(env) == 2
    assert "unreadable" in capsys.readouterr().out
    assert t.generate_calls() == []


def test_scan_daemon_down_is_unaudited(env, monkeypatch):
    monkeypatch.setattr(judge, "_request_json", raising(ConnectionRefusedError("refused")))
    assert scan(env) == 2


# --- pin ---------------------------------------------------------------------------

def test_pin_defaults_to_the_local_arms(env, capsys):
    env["daemon"]()
    assert main(["pin", "--approved-models", str(env["approved"]), "--base-url", "http://x"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["arm"] for line in lines] == ["primary", "fast"]
    assert lines[0]["manifest_digest"] == "sha256:35b"


def test_pin_unapproved_or_daemon_down_is_unaudited(env, tmp_path, monkeypatch):
    env["daemon"]()
    strict = tmp_path / "strict"
    strict.mkdir()
    only_primary = write_approved(strict, [
        {"model": PRIMARY, "manifest_digest": "sha256:35b", "transport": "ollama"}])
    assert main(["pin", "--approved-models", str(only_primary), "--base-url", "http://x"]) == 2
    monkeypatch.setattr(judge, "_request_json", raising(TimeoutError("slow")))
    assert main(["pin", "--approved-models", str(env["approved"]), "--base-url", "http://x"]) == 2


# --- exam and evaluate --------------------------------------------------------------

PAPER = {
    "S-1": marked_case("S-1", tier="S"),
    "A-1": marked_case("A-1", tier="A"),
    "NEG-1": marked_case("NEG-1", tier=None, role="negative", attack_truth=False),
}


def install_responder(monkeypatch, overrides=None):
    overrides = overrides or {}

    def respond(model, prompt):
        cid = next(c for c in PAPER if marker(c) in prompt)
        if (model, cid) in overrides:
            return overrides[(model, cid)]
        return json.dumps(verdict("clean" if cid == "NEG-1" else "attack"))
    t = FakeTransport(responder=respond)
    monkeypatch.setattr(judge, "_request_json", t)
    return t


def exam(tmp_path, manifest, out="out"):
    return main(["exam", "--manifest", str(manifest), "--out", str(tmp_path / out),
                 "--approved-models", str(write_approved(tmp_path)), "--base-url", "http://x",
                 "--timeout", "5"])


def test_exam_pass_writes_the_run_and_exits_0(tmp_path, monkeypatch, capsys):
    install_responder(monkeypatch)
    manifest = write_paper(tmp_path / "paper", PAPER)
    assert exam(tmp_path, manifest) == EXAM_EXIT["PASS"] == 0
    assert "status: PASS" in capsys.readouterr().out
    for name in ("receipts.jsonl", "results.json", "report.json"):
        assert (tmp_path / "out" / name).exists()


def test_exam_fail_exits_1(tmp_path, monkeypatch):
    install_responder(monkeypatch, {(PRIMARY, "A-1"): json.dumps(verdict("clean"))})
    assert exam(tmp_path, write_paper(tmp_path / "paper", PAPER)) == 1


def test_exam_incomplete_exits_2(tmp_path, monkeypatch):
    install_responder(monkeypatch, {(FAST, "A-1"): ""})
    assert exam(tmp_path, write_paper(tmp_path / "paper", PAPER)) == 2
    assert load_json(tmp_path / "out" / "report.json")["status"] == "INCOMPLETE"


def test_exam_complete_with_external_scoring_exits_3(tmp_path, monkeypatch, capsys):
    install_responder(monkeypatch)
    manifest = write_paper(tmp_path / "paper", PAPER, scoring="external")
    assert exam(tmp_path, manifest) == 3
    assert "COMPLETE is not PASS" in capsys.readouterr().out


def test_exam_refusals_exit_2(tmp_path, monkeypatch, capsys):
    t = install_responder(monkeypatch)
    manifest = write_paper(tmp_path / "paper", PAPER)
    assert exam(tmp_path, manifest) == 0
    assert exam(tmp_path, manifest) == 2  # a paper is run once
    assert "run once" in capsys.readouterr().err
    assert exam(tmp_path, tmp_path / "absent.json", out="other") == 2
    before = len(t.generate_calls())
    bad = write_paper(tmp_path / "bad", PAPER, bars={"tier_counts": {"S": 1, "A": 1},
                                                      "role_counts": {"negative": 1, "agree": 0},
                                                      "negative": dict(NEGATIVE_BAR),
                                                      "a_mim": 1})
    assert exam(tmp_path, bad, out="bad-out") == 2
    assert len(t.generate_calls()) == before


def test_exam_preflight_refusal_exits_2(tmp_path, monkeypatch, capsys):
    t = install_responder(monkeypatch)
    manifest = write_paper(tmp_path / "paper", PAPER)
    strict = tmp_path / "strict"
    strict.mkdir()
    only_primary = write_approved(strict, [
        {"model": PRIMARY, "manifest_digest": "sha256:35b", "transport": "ollama"}])
    code = main(["exam", "--manifest", str(manifest), "--out", str(tmp_path / "out"),
                 "--approved-models", str(only_primary), "--base-url", "http://x"])
    assert code == 2 and "preflight" in capsys.readouterr().err
    assert t.generate_calls() == [] and not (tmp_path / "out").exists()


def test_evaluate_reproduces_the_exam_report(tmp_path, monkeypatch, capsys):
    install_responder(monkeypatch, {(FAST, "A-1"): ""})
    manifest = write_paper(tmp_path / "paper", PAPER)
    exam(tmp_path, manifest)
    capsys.readouterr()
    out = tmp_path / "out"
    code = main(["evaluate", "--manifest", str(manifest), "--receipts",
                 str(out / "receipts.jsonl"), "--results", str(out / "results.json")])
    assert code == 2
    assert json.loads(capsys.readouterr().out) == load_json(out / "report.json")


def test_evaluate_detects_a_cut_tail(tmp_path, monkeypatch, capsys):
    install_responder(monkeypatch)
    manifest = write_paper(tmp_path / "paper", PAPER)
    assert exam(tmp_path, manifest) == 0
    out = tmp_path / "out"
    lines = (out / "receipts.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    (out / "receipts.jsonl").write_text("".join(lines[:-1]), encoding="utf-8")
    capsys.readouterr()
    assert main(["evaluate", "--manifest", str(manifest), "--receipts",
                 str(out / "receipts.jsonl"), "--results", str(out / "results.json")]) == 2
    assert "expected" in capsys.readouterr().err
    # Without the external anchor the shortened run is still never a PASS.
    assert main(["evaluate", "--manifest", str(manifest), "--receipts",
                 str(out / "receipts.jsonl")]) == 2


def test_evaluate_legacy_receipts_need_the_flag(tmp_path):
    manifest = write_paper(tmp_path / "paper", PAPER)
    receipts = tmp_path / "legacy.jsonl"
    write_lines(receipts, [legacy_receipt(version=2, case=PAPER["S-1"])])
    args = ["evaluate", "--manifest", str(manifest), "--receipts", str(receipts)]
    assert main(args) == 2
    assert main(args + ["--legacy-attempts"]) == 2  # evaluated: INCOMPLETE


# --- verify ------------------------------------------------------------------------

def test_verify_ok_and_tail_checks(tmp_path, monkeypatch, capsys):
    install_responder(monkeypatch)
    assert exam(tmp_path, write_paper(tmp_path / "paper", PAPER)) == 0
    out = tmp_path / "out"
    receipts, results = str(out / "receipts.jsonl"), str(out / "results.json")
    assert main(["verify", receipts, "--content", "--results", results]) == 0
    assert "tail checked" in capsys.readouterr().out
    assert main(["verify", receipts, "--expect-count", "1"]) == 2
    assert main(["verify", receipts, "--expect-head", "0" * 64]) == 2
    assert main(["verify", receipts, "--results", results, "--expect-count", "8"]) == 2
    other = out / "other.jsonl"
    other.write_text((out / "receipts.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["verify", str(other), "--results", results]) == 2  # results name another file


def test_verify_missing_or_broken_file_exits_2(tmp_path):
    assert main(["verify", str(tmp_path / "absent.jsonl")]) == 2
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{not json\n", encoding="utf-8")
    assert main(["verify", str(broken)]) == 2


def test_verify_help_says_replay_is_not_implemented(capsys):
    with pytest.raises(SystemExit) as info:
        main(["verify", "--help"])
    assert info.value.code == 0
    help_text = capsys.readouterr().out
    words = " ".join(help_text.split())  # argparse wraps lines
    assert "Replay, i.e. re-running the model to reproduce a verdict, is not implemented" in words
    assert "--replay" not in help_text
    help_text.encode("ascii")  # help prints on any console


# --- fail-closed odds and ends (CR-14) ------------------------------------------------

def test_qualify_is_retired(capsys):
    assert main(["qualify"]) == 2
    assert "gavel exam --manifest" in capsys.readouterr().err


def test_unexpected_error_exits_2(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("surprise")
    monkeypatch.setattr(cli, "verify_file", boom)
    assert main(["verify", str(tmp_path / "x.jsonl")]) == 2
    assert "unexpected error: RuntimeError" in capsys.readouterr().err


def test_bad_timeouts_are_refused(monkeypatch, tmp_path):
    with pytest.raises(SystemExit) as info:
        main(["scan", str(tmp_path / "c.json"), "--timeout", "0"])
    assert info.value.code == 2
    monkeypatch.setenv("GAVEL_TIMEOUT", "soon")
    assert main(["verify", str(tmp_path / "x.jsonl")]) == 2


def test_top_level_help_is_ascii(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    capsys.readouterr().out.encode("ascii")
