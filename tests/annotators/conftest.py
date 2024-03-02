from pathlib import Path

import pytest
from unittest.mock import patch


"""
NOTE: These tests use the repo-level ragdaemon db, which is not ideal.
Some of the functions require a DB record to be present. This means the
tests will fail the first time, then will pass. My attempt to fix it by
overwriting in cwd here hasn't worked.
"""
@pytest.fixture
def cwd():
    test_cwd = Path("tests/sample")
    with patch('ragdaemon.utils.ragdaemon_dir', new=test_cwd):
        yield test_cwd

@pytest.fixture
def mock_get_llm_response():
    with patch('ragdaemon.annotators.chunker.get_llm_response', return_value={"chunks": []}) as mock:
        yield mock
