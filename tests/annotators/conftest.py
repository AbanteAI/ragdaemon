from pathlib import Path

import pytest


@pytest.fixture
def cwd():
    return Path("tests/sample")
