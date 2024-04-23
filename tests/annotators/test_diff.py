import json

import pytest
from networkx.readwrite import json_graph

from ragdaemon.annotators.diff import Diff, get_chunks_from_diff, parse_diff_id
from ragdaemon.context import ContextBuilder
from ragdaemon.daemon import Daemon
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import get_git_diff


def test_diff_get_chunks_from_diff(git_history):
    diff = get_git_diff("HEAD", cwd=git_history)
    actual = get_chunks_from_diff("HEAD", diff)
    expected = {
        "HEAD:main.py": "HEAD:5-28",
        "HEAD:src/operations.py:1-5": "HEAD:33-41",
        "HEAD:src/operations.py:8-10": "HEAD:42-47",
    }
    assert actual == expected


def test_diff_parse_diff_id():
    tests = [
        ("HEAD", "HEAD", "None", None),
        ("DEFAULT:main.py", "DEFAULT", "main.py", None),
        ("HEAD HEAD~1:path/to/file:1-2", "HEAD HEAD~1", "path/to/file", {1, 2}),
    ]
    for id, expected_ref, expected_path, expected_lines in tests:
        actual_ref, actual_path, actual_lines = parse_diff_id(id)
        actual_path = actual_path.as_posix() if actual_path else "None"
        assert actual_ref == expected_ref
        assert actual_path == expected_path
        assert actual_lines == expected_lines


@pytest.mark.asyncio
async def test_diff_annotate(git_history, mock_db):
    graph = KnowledgeGraph.load("tests/data/hierarchy_graph.json")
    graph.graph["cwd"] = git_history.as_posix()
    annotator = Diff()
    actual = await annotator.annotate(graph, mock_db)
    actual_nodes = {n for n, d in actual.nodes(data=True) if d and d["type"] == "diff"}

    with open("tests/data/diff_graph.json", "r") as f:
        data = json.load(f)
        expected = json_graph.node_link_graph(data)
    expected_nodes = {
        n for n, d in expected.nodes(data=True) if d and d["type"] == "diff"
    }

    assert actual_nodes == expected_nodes


@pytest.mark.asyncio
async def test_diff_render(git_history, mock_db):
    daemon = Daemon(cwd=git_history)
    await daemon.update(refresh=True)

    # Only diffs
    context = ContextBuilder(daemon.graph, daemon.db)
    context.add_diff("DEFAULT:main.py")
    context.add_diff("DEFAULT:src/operations.py:1-5")
    context.add_diff("DEFAULT:src/operations.py:8-10")
    actual = context.render(use_tags=True)
    assert (
        actual
        == """\
main.py (diff)
--git diff
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

src/operations.py (diff)
--git diff
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
-    return a - b
+return a - b #modified
 
"""
    )

    # Diffs with files and chunks
    context.remove_diff("DEFAULT:main.py")
    context.add_diff("DEFAULT:src/operations.py:1-5")
    context.add_ref("src/operations.py", tags=["user-included"])
    actual = context.render(use_tags=True)
    assert (
        actual
        == """\
src/operations.py (diff, user-included)
1:import math
2: #modified
3: #modified
4:def add(a, b): #modified
5:    return a + b
6:
7:
8:def subtract(a, b):
9:return a - b #modified
10:
11:
12:def multiply(a, b):
13:    return a * b
14:
15:
16:def divide(a, b):
17:    return a / b
18:
19:
20:def sqrt(a):
21:    return math.sqrt(a)
--git diff
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
-    return a - b
+return a - b #modified
 
"""
    )
