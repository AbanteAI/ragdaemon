from pathlib import Path

import pytest
from unittest.mock import patch


"""
NOTE: Some of the functions require a DB record to be present. This means the
tests will fail the first time, then will pass. This is not ideal.
"""


@pytest.fixture
def cwd():
    return Path("tests/sample")


@pytest.fixture
def mock_get_llm_response():
    with patch(
        "ragdaemon.annotators.chunker.get_llm_response", return_value={"chunks": []}
    ) as mock:
        yield mock
