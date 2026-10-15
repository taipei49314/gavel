"""The agy (informed, cloud) transport: CR-08, CR-09, CR-13.

No real agy is started: gavel.judge._popen is replaced by a fake that
records how it was called and writes canned output into the stdout and
stderr files the transport hands it.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import gavel
import pytest
from fakes import make_diff_case, verdict, write_approved
from gavel import judge
from gavel.judge import AGY_MAX_COMMAND_UNITS, UnauditedError, agy_generate
from gavel.prompt import MECHANISM_CLASSES
from gavel.qualify import judge_case
from gavel.receipts import ReceiptLog, build_receipt, verify_file

INFORMED = "gemini-4-argon-high"
EXE_BYTES = b"MZ fake agy executable"
REPO_ROOT = Path(gavel.__file__).resolve().parent.parent


def fake_popen(stdout=b"", stderr=b"", code=0, hang=False, start_error=None):
    calls = []

    class Proc:
        def __init__(self, argv, **kw):
            if start_error is not None:
                raise start_error
            calls.append({"argv": list(argv), **kw,
                          "cwd_entries": sorted(os.listdir(kw["cwd"])), "killed": False})
            kw["stdout"].write(stdout)
            kw["stdout"].flush()
            kw["stderr"].write(stderr)
            kw["stderr"].flush()

        def wait(self, timeout=None):
            if hang and not calls[-1]["killed"]:
                raise subprocess.TimeoutExpired("agy", timeout)
            return code

        def kill(self):
            calls[-1]["killed"] = True

    return Proc, calls


@pytest.fixture
def agy_exe(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "agy.exe"
    exe.parent.mkdir()
    exe.write_bytes(EXE_BYTES)
    monkeypatch.setenv("GAVEL_AGY", str(exe))
    return exe


def install(monkeypatch, **kw):
    proc, calls = fake_popen(**kw)
    monkeypatch.setattr(judge, "_popen", proc)
    return calls


CLEAN = json.dumps(verdict("clean"))


def test_runs_in_a_fresh_empty_directory_without_a_shell(agy_exe, monkeypatch):
    calls = install(monkeypatch, stdout=CLEAN.encode() + b"\n")
    out = agy_generate(INFORMED, "the prompt", timeout_s=5)
    call = calls[0]
    assert call["argv"] == [str(agy_exe.resolve()), "-p", "the prompt", "--model", INFORMED]
    assert call["shell"] is False and call["stdin"] == subprocess.DEVNULL
    assert call["cwd_entries"] == []
    cwd = Path(call["cwd"]).resolve()
    assert cwd != Path.cwd().resolve() and REPO_ROOT not in (cwd, *cwd.parents)
    assert not cwd.exists()  # removed after the call
    assert out["raw"] == CLEAN + "\n"
    assert out["generation"] == {"exit_code": 0}


def test_records_the_executable_hash_and_source(agy_exe, monkeypatch):
    install(monkeypatch, stdout=CLEAN.encode())
    version = agy_generate(INFORMED, "p", timeout_s=5)["transport_version"]
    assert version["executable_sha256"] == hashlib.sha256(EXE_BYTES).hexdigest()
    assert version["executable_source"] == "GAVEL_AGY"
    assert version["executable"].endswith("bin/agy.exe")
    assert version["cwd"] == "fresh empty temporary directory"
    assert version["prompt_channel"] == "argv"


def test_home_directory_is_written_as_tilde(agy_exe, monkeypatch, tmp_path):
    home = str(tmp_path.resolve())
    monkeypatch.setenv("USERPROFILE", home)
    monkeypatch.setenv("HOME", home)
    install(monkeypatch, stdout=CLEAN.encode())
    version = agy_generate(INFORMED, "p", timeout_s=5)["transport_version"]
    assert version["executable"] == "~/bin/agy.exe"


def test_default_path_is_under_localappdata(tmp_path, monkeypatch):
    exe = tmp_path / "agy" / "bin" / "agy.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(EXE_BYTES)
    monkeypatch.delenv("GAVEL_AGY", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls = install(monkeypatch, stdout=CLEAN.encode())
    out = agy_generate(INFORMED, "p", timeout_s=5)
    assert out["transport_version"]["executable_source"] == "default"
    assert calls[0]["argv"][0] == str(exe.resolve())


@pytest.mark.parametrize("name", ["agy.cmd", "agy.bat", "AGY.CMD"])
def test_shell_scripts_are_never_run(tmp_path, monkeypatch, name):
    script = tmp_path / name
    script.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setenv("GAVEL_AGY", str(script))
    calls = install(monkeypatch, stdout=CLEAN.encode())
    with pytest.raises(UnauditedError, match="not accepted"):
        agy_generate(INFORMED, "p", timeout_s=5)
    assert calls == []


def test_relative_or_missing_or_unconfigured_executable_is_unaudited(tmp_path, monkeypatch):
    calls = install(monkeypatch, stdout=CLEAN.encode())
    monkeypatch.setenv("GAVEL_AGY", "agy.exe")
    with pytest.raises(UnauditedError, match="absolute path"):
        agy_generate(INFORMED, "p", timeout_s=5)
    monkeypatch.setenv("GAVEL_AGY", str(tmp_path / "absent" / "agy.exe"))
    with pytest.raises(UnauditedError, match="missing or unreadable"):
        agy_generate(INFORMED, "p", timeout_s=5)
    monkeypatch.delenv("GAVEL_AGY")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(UnauditedError, match="not configured"):
        agy_generate(INFORMED, "p", timeout_s=5)
    assert calls == []


@pytest.mark.parametrize("prompt", [
    "x" * (AGY_MAX_COMMAND_UNITS + 1),
    '"' * (AGY_MAX_COMMAND_UNITS // 2 + 10),  # each quote is escaped on the command line
])
def test_oversized_prompt_is_unaudited_before_anything_starts(agy_exe, monkeypatch, prompt):
    calls = install(monkeypatch, stdout=CLEAN.encode())
    with pytest.raises(UnauditedError, match="prompt too long") as info:
        agy_generate(INFORMED, prompt, timeout_s=5)
    assert calls == []
    assert info.value.transport_version["executable_sha256"] == hashlib.sha256(EXE_BYTES).hexdigest()


def test_timeout_kills_the_process_and_is_unaudited(agy_exe, monkeypatch):
    calls = install(monkeypatch, stdout=b"partial", hang=True)
    with pytest.raises(UnauditedError, match="timeout") as info:
        agy_generate(INFORMED, "p", timeout_s=0.01)
    assert calls[0]["killed"] is True
    assert info.value.transport_version is not None


def test_output_that_is_not_utf8_is_unaudited_and_kept(agy_exe, monkeypatch):
    install(monkeypatch, stdout=b'\xff{"verdict": "clean"}')
    with pytest.raises(UnauditedError, match="not valid UTF-8") as info:
        agy_generate(INFORMED, "p", timeout_s=5)
    assert info.value.raw.startswith("\\xff")


def test_nonzero_exit_keeps_stdout(agy_exe, monkeypatch):
    install(monkeypatch, stdout=b"partial answer", stderr=b"boom", code=3)
    with pytest.raises(UnauditedError, match="agy exit 3: boom") as info:
        agy_generate(INFORMED, "p", timeout_s=5)
    assert info.value.raw == "partial answer"
    assert info.value.generation == {"exit_code": 3}


def test_empty_output_and_start_failure_are_unaudited(agy_exe, monkeypatch):
    install(monkeypatch, stdout=b"  \n")
    with pytest.raises(UnauditedError, match="empty agy response"):
        agy_generate(INFORMED, "p", timeout_s=5)
    install(monkeypatch, start_error=OSError("cannot start"))
    with pytest.raises(UnauditedError, match="could not be started"):
        agy_generate(INFORMED, "p", timeout_s=5)


# --- through the judgment path and into a receipt -------------------------------------

def test_judge_case_sends_the_informed_arm_to_agy(agy_exe, monkeypatch, tmp_path):
    calls = install(monkeypatch, stdout=CLEAN.encode())
    res = judge_case(make_diff_case(), INFORMED, "http://127.0.0.1:11434", 5,
                     approved_models=write_approved(tmp_path), transport_name="agy")
    assert res["unaudited"] is None and res["verdict"]["verdict"] == "clean"
    assert len(calls) == 1 and calls[0]["argv"][-1] == INFORMED
    assert calls[0]["argv"][2] == res["prompt_text"]
    # Execution is recorded truthfully: no Ollama base URL, no temperature.
    assert res["execution"] == {"timeout_s": 5} and res["options"] == {}
    assert res["transport"]["name"] == "agy"
    assert res["transport"]["version"]["executable_sha256"] == hashlib.sha256(EXE_BYTES).hexdigest()
    path = tmp_path / "receipts.jsonl"
    ReceiptLog(path).append(build_receipt(case_id="T-1", arm="informed", run=1, attempt=1,
                                          judgment=res))
    rec = verify_file(path, MECHANISM_CLASSES, content=True)[0]
    assert rec["transport"]["version"]["executable_source"] == "GAVEL_AGY"


def test_failed_agy_call_still_records_the_executable(agy_exe, monkeypatch, tmp_path):
    install(monkeypatch, stdout=b"", stderr=b"quota", code=1)
    res = judge_case(make_diff_case(), INFORMED, "http://x", 5,
                     approved_models=write_approved(tmp_path), transport_name="agy")
    assert res["verdict"] is None and res["unaudited"].startswith("agy exit 1")
    assert res["transport"]["version"]["executable_sha256"] == hashlib.sha256(EXE_BYTES).hexdigest()
    assert res["generation"] == {"exit_code": 1}
