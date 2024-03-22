import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

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


@pytest.fixture(scope="function")
def git_history(cwd):
    # Copy the way it's done in mentat
    temp_dir = os.path.realpath(tempfile.mkdtemp())

    tmpdir_path = Path(temp_dir)
    sample_dir = cwd
    shutil.copytree(sample_dir, tmpdir_path, dirs_exist_ok=True)
    # TODO: Use/save .ragdaemon records

    # Initial commit
    subprocess.run(["git", "init"], cwd=tmpdir_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "you@example.com"],
        cwd=tmpdir_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Your Name"], cwd=tmpdir_path, check=True
    )
    subprocess.run(["git", "add", "."], cwd=tmpdir_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=tmpdir_path, check=True
    )

    # Diff
    modify_lines = [1, 2, 3, 8]  # Modify
    with open(tmpdir_path / "src" / "operations.py", "r") as f:
        lines = f.readlines()
    for i in modify_lines:
        lines[i] = lines[i].strip() + " #modified\n"
    with open(tmpdir_path / "src" / "operations.py", "w") as f:
        f.writelines(lines)
    (tmpdir_path / "main.py").unlink()  # Remove
    with open(tmpdir_path / "hello.py", "w") as f:  # Add
        f.write("print('Hello, world!')\n")

    yield tmpdir_path 

    # Retry deletion with a delay
    retries = 3
    delay = 1
    for attempt in range(retries):
        try:
            shutil.rmtree(tmpdir_path)
            break
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
