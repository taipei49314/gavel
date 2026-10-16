"""tools/round3_run.py (round-3 PREREG draft, sections 2, 4 and 8): the PJU
runner refuses a non-local arm, an unpinned runtime or missing options; runs
a paper only into a fresh run directory and never again once receipts exist;
and runs only the lock commit's harness (clean tree, lock commit on a remote
branch, later changes only under results/round-3/, not on main)."""

import importlib.util
import json
import subprocess
from pathlib import Path

import gavel
import pytest

REPO_ROOT = Path(gavel.__file__).resolve().parent.parent


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "round3_run", REPO_ROOT / "tools" / "round3_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


round3_run = _load_tool()


def _manifest(tmp_path, **changes):
    manifest = {"arms": {"primary": {"model": "qwen3.5:35b-a3b", "transport": "ollama",
                                     "runs": {"default": 1}}},
                "runtime": {"ollama_version": round3_run.OLLAMA_VERSION},
                "options": {"temperature": 0, "num_ctx": 16384}}
    manifest.update(changes)
    path = tmp_path / "paper.manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_committed_papers_pass_the_manifest_checks():
    for rel in round3_run.PAPERS.values():
        manifest = round3_run.check_manifest(REPO_ROOT / rel)
        assert manifest["gating_arm"] in manifest["arms"]
        assert len(manifest["arms"]) == 1  # completeness option (B): one arm per paper


@pytest.mark.parametrize("changes, message", [
    ({"arms": {"informed": {"model": "m", "transport": "agy", "runs": {"default": 1}}}},
     "not local"),
    ({"runtime": {"ollama_version": "0.35.0"}}, "does not pin"),
    ({"runtime": None}, "does not pin"),
    ({"options": {}}, "options"),
])
def test_manifest_checks_refuse(tmp_path, changes, message):
    with pytest.raises(round3_run.Refused, match=message):
        round3_run.check_manifest(_manifest(tmp_path, **changes))


def test_next_run_counts_runs_that_judged_nothing(tmp_path):
    paper = tmp_path / "R"
    assert round3_run.next_run(paper) == 1
    (paper / "run-1").mkdir(parents=True)
    (paper / "run-1" / "START.json").write_text("{}", encoding="utf-8")
    assert round3_run.next_run(paper) == 2


def test_next_run_refuses_a_paper_with_receipts(tmp_path):
    run = tmp_path / "R" / "run-1"
    run.mkdir(parents=True)
    (run / "receipts.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(round3_run.Refused, match="run once"):
        round3_run.next_run(tmp_path / "R")


def test_main_refuses_while_the_papers_are_not_locked(capsys):
    assert round3_run.JUDGMENT_TIMEOUT_S is None
    assert round3_run.main(["R", "--lock-commit", "HEAD"]) == 2
    assert "not locked" in capsys.readouterr().err


# --- check_harness on a scratch repository ----------------------------------

def _git(root, *args):
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _commit(root, rel, text, message):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", rel)
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"
                       }.items():
        monkeypatch.setenv(key, value)
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "config", "core.autocrlf", "false")
    _git(work, "remote", "add", "origin", str(origin))
    lock = _commit(work, "gavel/harness.py", "x = 1\n", "lock")
    _git(work, "push", "-q", "origin", "main")
    _git(work, "switch", "-q", "-c", "round-3/run")
    return work, lock


def test_harness_accepts_run_records_after_the_lock(repo):
    work, lock = repo
    _commit(work, "results/round-3/R/run-1/START.json", "{}\n", "start")
    found = round3_run.check_harness(lock, root=work)
    assert found["lock_commit"] == lock and found["branch"] == "round-3/run"


def test_harness_refuses_a_change_outside_the_run_records(repo):
    work, lock = repo
    _commit(work, "gavel/harness.py", "x = 2\n", "edit")
    with pytest.raises(round3_run.Refused, match="outside results/round-3"):
        round3_run.check_harness(lock, root=work)


def test_harness_refuses_untracked_and_uncommitted_files(repo):
    work, lock = repo
    (work / "gavel" / "shadow.py").write_text("", encoding="utf-8")
    with pytest.raises(round3_run.Refused, match="untracked"):
        round3_run.check_harness(lock, root=work)


def test_harness_refuses_a_lock_commit_that_was_not_pushed(repo):
    work, _ = repo
    unpushed = _commit(work, "gavel/harness.py", "x = 3\n", "not pushed")
    with pytest.raises(round3_run.Refused, match="not on any remote branch"):
        round3_run.check_harness(unpushed, root=work)


def test_harness_refuses_a_lock_commit_that_is_not_an_ancestor(repo):
    work, lock = repo
    _git(work, "switch", "-q", "--orphan", "other")
    _commit(work, "README.md", "other\n", "unrelated")
    with pytest.raises(round3_run.Refused, match="not an ancestor"):
        round3_run.check_harness(lock, root=work)


def test_harness_refuses_main(repo):
    work, lock = repo
    _git(work, "switch", "-q", "main")
    with pytest.raises(round3_run.Refused, match="not pushed to main"):
        round3_run.check_harness(lock, root=work)


# --- load conditions ---------------------------------------------------------

def test_unload_all_unloads_every_loaded_model_and_waits(monkeypatch):
    loaded = [{"name": "qwen3.5:35b-a3b"}, {"name": "qwen3.5:9b"}]
    requests = []

    def fake_ollama(path, payload=None, timeout=120):
        if path == "/api/ps":
            return {"models": list(loaded)}
        requests.append(payload)
        loaded[:] = [m for m in loaded if m["name"] != payload["model"]]
        return {"done": True}

    monkeypatch.setattr(round3_run, "ollama", fake_ollama)
    before = round3_run.unload_all()
    assert [m["name"] for m in before] == ["qwen3.5:35b-a3b", "qwen3.5:9b"]
    assert requests == [{"model": "qwen3.5:35b-a3b", "keep_alive": 0},
                        {"model": "qwen3.5:9b", "keep_alive": 0}]
    assert round3_run.loaded_models() == []


def test_unload_all_refuses_when_a_model_stays_loaded(monkeypatch):
    monkeypatch.setattr(round3_run, "ollama",
                        lambda path, payload=None, timeout=120: {"models": [{"name": "m"}]})
    monkeypatch.setattr(round3_run.time, "sleep", lambda s: None)
    with pytest.raises(round3_run.Refused, match="still loaded"):
        round3_run.unload_all(deadline_s=0)


def test_load_lines_keep_the_model_load_lines_written_after_the_offset(tmp_path):
    log = tmp_path / "server.log"
    log.write_bytes(b"load_tensors: old\n")
    offset = log.stat().st_size
    with open(log, "ab") as fh:
        fh.write(b"[GIN] 200 /api/generate\nload_tensors: offloaded 34/34 layers to GPU\n"
                 b"llama_kv_cache: size = 272.00 MiB\nsrv update_slots: idle\n")
    assert round3_run.load_lines(log, offset) == (
        "load_tensors: offloaded 34/34 layers to GPU\nllama_kv_cache: size = 272.00 MiB\n")
    assert "unreadable" in round3_run.load_lines(tmp_path / "missing.log", 0)
