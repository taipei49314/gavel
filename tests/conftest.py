import pytest

import gavel.judge
from gavel.prompt import MECHANISM_CLASSES


@pytest.fixture
def mechanism_classes():
    return list(MECHANISM_CLASSES)


def _no_daemon(*args, **kwargs):
    raise OSError("tests never reach a daemon")


def _no_agy(*args, **kwargs):
    raise OSError("tests never start agy")


@pytest.fixture(autouse=True)
def _isolated_gavel_env(monkeypatch, tmp_path_factory):
    """The host's GAVEL_* settings never leak into a test (CLI defaults are
    read from them), and a test that forgets to install a fake transport
    fails closed instead of reaching a real daemon or a real agy.

    workloads/gavel_verify/run.py points GAVEL_OLLAMA at a closed port and
    GAVEL_AGY at a missing file for the same reason; this fixture removes
    those variables, so it restores the defence here: GAVEL_AGY names a file
    that does not exist, and the Ollama HTTP call (judge._request_json) and
    the agy process start (judge._popen) raise OSError, which the transports
    turn into UNAUDITED. Tests that need either install their own fake
    through monkeypatch afterwards, which overrides these.
    """
    for name in ("GAVEL_TIMEOUT", "GAVEL_OLLAMA", "GAVEL_APPROVED_MODELS", "GAVEL_AGY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GAVEL_AGY", str(tmp_path_factory.getbasetemp() / "no-agy" / "agy.exe"))
    monkeypatch.setattr(gavel.judge, "_request_json", _no_daemon)
    monkeypatch.setattr(gavel.judge, "_popen", _no_agy)
