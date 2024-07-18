import io as _io
import os
import platform
import shutil
import subprocess
import tarfile
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
def cwd_git(cwd):
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
        yield tmpdir_path


@pytest.fixture(scope="function")
def cwd_git_diff(cwd_git):
    modify_lines = [1, 2, 3, 8]  # Modify
    with open(cwd_git / "src" / "operations.py", "r") as f:
        lines = f.readlines()
    for i in modify_lines:
        lines[i] = lines[i].strip() + " #modified\n"
    with open(cwd_git / "src" / "operations.py", "w") as f:
        f.writelines(lines)
    (cwd_git / "main.py").unlink()  # Remove
    with open(cwd_git / "hello.py", "w") as f:  # Add
        f.write("print('Hello, world!')\n")

    yield cwd_git


# We have to set the key since counting tokens with an openai model loads the openai client
@pytest.fixture(autouse=True)
def mock_openai_api_key():
    os.environ["OPENAI_API_KEY"] = "fake_key"


"""
GithubActions for Linux comes with Docker pre-installed.
Setting up a Docker environment for MacOS and Windows in Github Actions is tedious.
The purpose of supporting docker IO is for butler, which only runs on Linux anyway,
so we can skip these tests on MacOS and Windows. We still make an attempt though,
because if Docker IS installed (i.e. local development on MacOS or Windows), it should
still work.
"""
def fail_silently_on_macos_and_windows(docker_function, *args, **kwargs):
    try:
        return docker_function(*args, **kwargs)
    except DockerException as e:
        if platform.system() in ["Darwin", "Windows"]:
            pytest.skip(f"Skipping Docker tests on {platform.system()} due to Docker error: {e}")
        else:
            raise e   


@pytest.fixture(scope="session")
def docker_client():
    return fail_silently_on_macos_and_windows(docker.from_env)


@pytest.fixture
def container(cwd, docker_client, path="tests/sample"):
    image = "python:3.10"
    container = fail_silently_on_macos_and_windows(
        docker_client.containers.run, image, detach=True, tty=True, command="sh"
    )

    # Create the tests/sample directory in the container
    container.exec_run(f"mkdir -p {path}")

    # Copy everything in cwd into the docker container at the same location
    tarstream = _io.BytesIO()
    with tarfile.open(fileobj=tarstream, mode="w") as tar:
        tar.add(cwd, arcname=".")
    tarstream.seek(0)
    container.put_archive(path, tarstream)

    workdir = f"/{path}"
    container.exec_run("git init", workdir=workdir)
    container.exec_run("git config user.email you@example.com", workdir=workdir)
    container.exec_run("git config user.name 'Your Name'", workdir=workdir)

    try:
        yield container
    finally:
        container.stop()
        container.remove()
