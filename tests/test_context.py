from pathlib import Path

import pytest

from ragdaemon.context import ContextBuilder
from ragdaemon.daemon import Daemon
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import get_document


def test_daemon_render_context(cwd, mock_db):
    path_str = Path("src/interface.py").as_posix()
    ref = path_str

    # Base Chunk
    context = ContextBuilder(KnowledgeGraph(), mock_db)
    context.context = {
        path_str: {
            "lines": set([1, 2, 3, 4, 15]),
            "tags": ["test-flag"],
            "document": get_document(ref, cwd),
            "diffs": set(),
            "comments": dict(),
        }
    }
    actual = context.render(use_tags=True)
    assert (
        actual
        == """\
src/interface.py (test-flag)
1:import argparse
2:import re
3:
4:
...
15:
...
"""
    )

    # Function Chunk
    context.context = {
        path_str: {
            "lines": set([5, 6, 7, 8, 9, 10, 11, 12, 13, 14]),
            "tags": ["test-flag"],
            "document": get_document(ref, cwd),
            "diffs": set(),
            "comments": dict(),
        }
    }
    actual = context.render(use_tags=True)
    assert (
        actual
        == """\
src/interface.py (test-flag)
...
5:def parse_arguments():
6:    parser = argparse.ArgumentParser(description="Basic Calculator")
7:    parser.add_argument("operation", type=str, help="Calculation operation")
8:    args = parser.parse_args()
9:
10:    # use re to parse symbol, nubmer before, nubmer after
11:    match = re.match(r"(\\d+)(\\D)(\\d+)", args.operation)
12:    if match is None:
13:        raise ValueError("Invalid operation")
14:    return int(match.group(1)), match.group(2), int(match.group(3))
...
"""
    )


@pytest.mark.asyncio
async def test_context_builder_methods(cwd, mock_db):
    daemon = Daemon(cwd)
    await daemon.update()

    context = daemon.get_context("")
    context.add_ref("src/interface.py:3-5")

    copied_context = context.copy()
    copied_context.add_ref("src/interface.py:7-9")

    assert context.context["src/interface.py"]["lines"] == set([3, 4, 5])
    assert copied_context.context["src/interface.py"]["lines"] == set(
        [3, 4, 5, 7, 8, 9]
    )

    different_context = daemon.get_context("")
    different_context.add_ref("src/interface.py:17")
    different_context.add_ref("src/operations.py")
    combined_context = context + different_context

    assert combined_context.context["src/interface.py"]["lines"] == set([3, 4, 5, 17])
    assert combined_context.context["src/operations.py"]["lines"] == set(range(1, 22))


def test_to_refs(cwd, mock_db):
    path_str = Path("src/interface.py").as_posix()
    ref = path_str

    # Setup Context
    context = ContextBuilder(KnowledgeGraph(), mock_db)
    context.context = {
        path_str: {
            "lines": set([1, 2, 3, 4, 15]),
            "tags": ["test-flag"],
            "document": get_document(ref, cwd),
            "diffs": set(),
            "comments": dict(),
        }
    }
    expected_refs = [f"{path_str}:1-4,15-15"]
    actual_refs = context.to_refs()
    assert actual_refs == expected_refs, f"Expected {expected_refs}, got {actual_refs}"
