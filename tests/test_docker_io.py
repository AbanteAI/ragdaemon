import io as _io
import tarfile
from pathlib import Path

import pytest

from ragdaemon.daemon import Daemon


@pytest.fixture
def path():
    return "tests/sample"


@pytest.fixture
def container(git_history, docker_client, path):
    image = "python:3.10"
    container = docker_client.containers.run(image, detach=True, tty=True, command="sh")

    # Create the tests/sample directory in the container
    container.exec_run(f"mkdir -p {path}")

    # Copy everything in cwd into the docker container at the same location
    tarstream = _io.BytesIO()
    with tarfile.open(fileobj=tarstream, mode="w") as tar:
        tar.add(git_history, arcname=".")
    tarstream.seek(0)
    container.put_archive(path, tarstream)

    # Because git repo was copied from outside, need to add this otherwise it's suspicious
    container.exec_run(f"git config --global --add safe.directory /{path}")

    try:
        yield container
    finally:
        container.stop()
        container.remove()


def get_message_chunk_set(message):  # Because order can vary
    chunks = message.split("\n\n")
    if len(chunks) > 0:
        for i in range(len(chunks) - 1):
            chunks[i] += "\n"


@pytest.mark.asyncio
async def test_docker_io(container, path):
    daemon = Daemon(Path(path), annotators={"hierarchy": {}}, container=container)
    await daemon.update()

    actual = daemon.get_context("test", max_tokens=1000).render(use_tags=True)

    with open("tests/data/context_message.txt", "r") as f:
        expected = f.read()
    assert get_message_chunk_set(actual) == get_message_chunk_set(expected)

    # Included Files
    context = daemon.get_context("test")
    context.add_ref("src/interface.py:11-12", tags=["user-included"])
    actual = daemon.get_context("test", context_builder=context, auto_tokens=0).render(
        use_tags=True
    )
    assert (
        actual
        == """\
src/interface.py (user-included)
...
11:    match = re.match(r"(\\d+)(\\D)(\\d+)", args.operation)
12:    if match is None:
...
"""
    )
