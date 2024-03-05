import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from ragdaemon.annotators.diff import (
    get_chunks_from_diff, parse_diff_id, Diff,
)
from ragdaemon.utils import get_git_diff


@pytest.fixture(scope="function")
def git_history(cwd):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        sample_dir = cwd
        shutil.copytree(sample_dir, tmpdir_path, dirs_exist_ok=True)

        # Initial commit
        subprocess.run(["git", "init"], cwd=tmpdir_path, check=True)
        subprocess.run(["git", "config", "user.email", "you@example.com"], cwd=tmpdir_path, check=True)
        subprocess.run(["git", "config", "user.name", "Your Name"], cwd=tmpdir_path, check=True)
        subprocess.run(["git", "add", "."], cwd=tmpdir_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmpdir_path, check=True)

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

        # No need to revert changes, temporary directory will be deleted


def test_diff_get_chunks_from_diff(git_history):
    diff = get_git_diff("HEAD", cwd=git_history)
    actual = get_chunks_from_diff("HEAD", diff)
    expected = {
        'HEAD:main.py': 'HEAD:5-28', 
        'HEAD:src/operations.py:1-5': 'HEAD:33-41', 
        'HEAD:src/operations.py:8-10': 'HEAD:42-47'
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
        assert actual_ref == expected_ref
        assert str(actual_path) == expected_path
        assert actual_lines == expected_lines


@pytest.mark.asyncio
async def test_diff_annotate(git_history):
    with open("tests/data/chunker_graph.json", "r") as f:
        data = json.load(f)
        graph = nx.readwrite.json_graph.node_link_graph(data)
    graph.graph["cwd"] = str(git_history)
    annotator = Diff()
    actual = await annotator.annotate(graph)
    actual_nodes = {n for n, d in actual.nodes(data=True) if d["type"] == "diff"}

    with open("tests/data/diff_graph.json", "r") as f:
        data = json.load(f)
        expected = nx.readwrite.json_graph.node_link_graph(data)
    expected_nodes = {n for n, d in expected.nodes(data=True) if d["type"] == "diff"}
    
    assert actual_nodes == expected_nodes
