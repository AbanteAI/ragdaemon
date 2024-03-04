import networkx as nx

from ragdaemon.utils import get_document
from ragdaemon.context import ContextBuilder


def test_daemon_render_context(cwd):
    path_str = "src/interface.py"
    ref = path_str

    # Base Chunk
    context = ContextBuilder(nx.MultiDiGraph())
    context.context = {
        path_str: {
            "lines": set([1, 2, 3, 4, 15]),
            "tags": ["test-flag"],
            "document": get_document(ref, cwd),
        }
    }
    actual = context.render()
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
        }
    }
    actual = context.render()
    assert (
        actual
        == """\
src/interface.py (test-flag)
...
5:def parse_arguments():
6:    parser = argparse.ArgumentParser(description="Basic Calculator")
7:    parser.add_argument("operation", type=str, help="Calculation operation (e.g., 3+4)")
8:    args = parser.parse_args()
9:
10:    # use re to parse symbol, nubmer before, nubmer after
11:    match = re.match(r"(\d+)(\D)(\d+)", args.operation)
12:    if match is None:
13:        raise ValueError("Invalid operation")
14:    return int(match.group(1)), match.group(2), int(match.group(3))
...
"""
    )
