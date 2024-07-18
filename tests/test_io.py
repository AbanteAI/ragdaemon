from pathlib import Path

import pytest

from ragdaemon.daemon import Daemon
from ragdaemon.io import DockerIO, IO, LocalIO


def all_io_methods(io: IO):
    text = "Hello, world!"

    with io.open("tempfile.txt", "w") as f:
        f.write(text)

    with io.open("tempfile.txt") as f:
        assert f.read() == text

    assert io.is_git_repo()

    assert io.last_modified("tempfile.txt") > 0

    assert io.get_git_diff() == ""

    io.mkdir("tempdir/tempsubdir", parents=True)
    assert io.exists("tempdir/tempsubdir")

    io.rename("tempdir/tempsubdir", "tempdir/renamedsubdir")
    assert io.exists("tempdir/renamedsubdir")

    io.unlink("tempfile.txt")
    assert not io.exists("tempfile.txt")


@pytest.mark.asyncio
async def test_local_io_methods(cwd_git):

    io = LocalIO(Path(cwd_git))
    all_io_methods(io)


@pytest.mark.asyncio
async def test_docker_io_methods(container):
    io = DockerIO(Path("tests/sample"), container=container)
    all_io_methods(io)


def get_message_chunk_set(message):  # Because order can vary
    chunks = message.split("\n\n")
    if len(chunks) > 0:
        for i in range(len(chunks) - 1):
            chunks[i] += "\n"


@pytest.mark.asyncio
async def test_docker_io_integration(container, path="tests/sample"):
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


"""
'diff --git a/main.py b/main.py
deleted file mode 100644
index fcabfbe..0000000
--- a/main.py
+++ /dev/null
@@ -1,23 +0,0 @@
-from src.interface import parse_arguments, render_response
-from src.operations import add, divide, multiply, subtract
-
-
-def main():
-    a, op, b = parse_arguments()
-
-    if op == "+":
-        result = add(a, b)
-    elif op == "-":
-        result = subtract(a, b)
-    elif op == "*":
-        result = multiply(a, b)
-    elif op == "/":
-        result = divide(a, b)
-    else:
-        raise ValueError("Unsupported operation")
-
-    render_response(result)
-
-
-if __name__ == "__main__":
-    main()
diff --git a/src/operations.py b/src/operations.py
index 9f1facd..073af81 100644
--- a/src/operations.py
+++ b/src/operations.py
@@ -1,5 +1,5 @@
 import math
-
-
-def add(a, b):
+ #modified
+ #modified
+def add(a, b): #modified
     return a + b
@@ -8,3 +8,3 @@ def add(a, b):
 def subtract(a, b):
-    return a - b\n+return a - b #modified\n \n'
"""
