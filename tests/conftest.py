import pytest

from gavel.prompt import MECHANISM_CLASSES


@pytest.fixture
def mechanism_classes():
    return list(MECHANISM_CLASSES)
