import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import docker
from docker.errors import DockerException
import pytest

from ragdaemon.database import DEFAULT_EMBEDDING_MODEL, get_db
from ragdaemon.io import LocalIO


@pytest.fixture
def cwd():
    return Path("tests/sample").resolve()


@pytest.fixture
def io(cwd):
    return LocalIO(cwd)


@pytest.fixture
def mock_db():
    return get_db(spice_client=AsyncMock(), embedding_model=DEFAULT_EMBEDDING_MODEL)


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


# We have to set the key since counting tokens with an openai model loads the openai client
@pytest.fixture(autouse=True)
def mock_openai_api_key():
    os.environ["OPENAI_API_KEY"] = "fake_key"


@pytest.fixture(scope="session")
def docker_client():
    return docker.from_env()


def pytest_runtest_call(item):
    if "uses_docker" in item.keywords:
        try:
            item.runtest()
        except DockerException as e:
            if platform.system() in ["Darwin", "Windows"]:
                pytest.skip(
                    f"Skipping Docker tests on {platform.system()} due to Docker error"
                )
            else:
                raise e
