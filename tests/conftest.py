import pytest

from gavel.prompt import MECHANISM_CLASSES


@pytest.fixture
def mechanism_classes():
    return list(MECHANISM_CLASSES)


@pytest.fixture(autouse=True)
def _isolated_gavel_env(monkeypatch):
    """The host's GAVEL_* settings never leak into a test (CLI defaults are
    read from them)."""
    for name in ("GAVEL_TIMEOUT", "GAVEL_OLLAMA", "GAVEL_APPROVED_MODELS", "GAVEL_AGY"):
        monkeypatch.delenv(name, raising=False)
