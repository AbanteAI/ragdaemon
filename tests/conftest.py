import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ragdaemon.database import set_db


@pytest.fixture
def cwd():
    return Path("tests/sample")


@pytest.fixture
def mock_set_db(cwd):
    set_db(cwd, AsyncMock())


@pytest.fixture
def mock_get_llm_response():
    with patch(
        "ragdaemon.annotators.chunker_llm.ChunkerLLM.get_llm_response",
        return_value={"chunks": []},
    ) as mock:
        yield mock


@pytest.fixture(scope="function")
def git_history(cwd):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
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
