import pytest

from ragdaemon.annotators.summarizer import (
    build_filetree,
    get_document_and_context,
)
from ragdaemon.daemon import Daemon
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import get_document


@pytest.mark.asyncio
async def test_build_filetree(cwd):
    daemon = Daemon(
        cwd=cwd,
        annotators={"hierarchy": {}},
    )
    await daemon.update(refresh=True)

    node_filetree = build_filetree(daemon.graph, "src/interface.py")
    assert node_filetree == [
        ".gitignore",
        "README.md",
        "main.py",
        "src (3 items)",
        "  src/__init__.py",
        "  <b>src/interface.py</b>",
        "  src/operations.py",
    ]

    dir_filetree = build_filetree(daemon.graph, "src")
    assert dir_filetree == [
        ".gitignore",
        "README.md",
        "main.py",
        "<b>src (3 items)</b>",
        "  src/__init__.py",
        "  src/interface.py",
        "  src/operations.py",
    ]


@pytest.mark.asyncio
async def test_get_document_and_context(io):
    graph = KnowledgeGraph.load("tests/data/summarizer_graph.json")  # Chunk data
    for _, data in graph.nodes(data=True):
        document = get_document(data["ref"], io, type=data["type"])
        data["document"] = document

    # A chunk
    document, context = get_document_and_context(
        "src/interface.py:parse_arguments", graph, io
    )
    assert (
        document
        == """\
src/interface.py
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

    assert (
        context
        == """\
src/interface.py (chunk context)
No action is described as the provided code only includes import statements. (summary)
1:import argparse
2:import re
3:
4:
...

main.py (call graph)
...
5:def main():
6:    a, op, b = parse_arguments()
7:
8:    if op == "+":
9:        result = add(a, b)
10:    elif op == "-":
11:        result = subtract(a, b)
12:    elif op == "*":
13:        result = multiply(a, b)
14:    elif op == "/":
15:        result = divide(a, b)
16:    else:
17:        raise ValueError("Unsupported operation")
18:
19:    render_response(result)
...
"""
    )

    # A file
    document, context = get_document_and_context("src/interface.py", graph, io)
    assert document.startswith("src/interface.py\n")
    assert (
        context
        == """\
<file_tree>
.gitignore - Manage exclusions for version control by specifying files and directories that Git should ignore, while ensuring the .gitignore file itself remains tracked.
README.md - Describe the application's experimental purpose in testing the limits of the treesitter parser.
main.py - Execute arithmetic operations based on command-line input and produce an output.
src (8 items) - Organize code modules for a simple arithmetic operations application. It includes files for initializing the package, parsing command-line input, and defining arithmetic operations.
  src/__init__.py - Establish the 'src' as a Python package to organize related modules concerning command-line based arithmetic operations, without adding any explicit functionality.
  <b>src/interface.py (2 items) - Parse command-line input to extract operands and an operator for arithmetic operations and display the output to the console.</b>
  src/operations.py (5 items) - Define basic arithmetic operations including addition, subtraction, multiplication, division, and square root calculation utilizing Python's math library.
</file_tree>

<chunk_summaries>
src/interface.py:BASE No action is described as the provided code only includes import statements.
src/interface.py:render_response Display the result of a mathematical operation to standard output.
src/interface.py:parse_arguments Parse command-line arguments into three components: an integer, a symbol representing a mathematical operation, and a second integer.
</chunk_summaries>
"""
    )

    # A directory
    document, context = get_document_and_context("src", graph, io)
    assert document == "Directory: src"
    assert (
        context
        == """\
<file_tree>
.gitignore - Manage exclusions for version control by specifying files and directories that Git should ignore, while ensuring the .gitignore file itself remains tracked.
README.md - Describe the application's experimental purpose in testing the limits of the treesitter parser.
main.py - Execute arithmetic operations based on command-line input and produce an output.
<b>src (8 items) - Organize code modules for a simple arithmetic operations application. It includes files for initializing the package, parsing command-line input, and defining arithmetic operations.</b>
  src/__init__.py - Establish the 'src' as a Python package to organize related modules concerning command-line based arithmetic operations, without adding any explicit functionality.
  src/interface.py (2 items) - Parse command-line input to extract operands and an operator for arithmetic operations and display the output to the console.
  src/operations.py (5 items) - Define basic arithmetic operations including addition, subtraction, multiplication, division, and square root calculation utilizing Python's math library.
</file_tree>"""
    )
