import json
from pathlib import Path

import networkx as nx
import pytest

from ragdaemon.annotators.hierarchy import Hierarchy, get_active_checksums


def test_get_active_checksums(cwd):
    checksums = get_active_checksums(cwd)
    assert isinstance(checksums, dict), "Checksums is not a dict"
    assert all(isinstance(k, Path) for k in checksums), "Keys are not all Paths"
    assert all(
        isinstance(v, str) for v in checksums.values()
    ), "Values are not all strings"

    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    expected = {
        (node, data["checksum"])
        for node, data in hierarchy_graph.nodes(data=True)
        if "checksum" in data
    }
    actual = {(path.as_posix(), checksum) for path, checksum in checksums.items()}
    assert actual == expected, "Checksums are not equal"


def test_hierarchy_is_complete(cwd):
    empty_graph = nx.MultiDiGraph()
    empty_graph.graph["cwd"] = cwd.as_posix()
    hierarchy = Hierarchy()

    assert not hierarchy.is_complete(empty_graph), "Empty graph should not be complete."
    incomplete_graph = empty_graph.copy()
    path_str = cwd.as_posix()
    incomplete_graph.add_node(path_str, path=path_str, type="directory", id=path_str)
    assert not hierarchy.is_complete(
        incomplete_graph
    ), "Incomplete graph should not be complete"

    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert hierarchy.is_complete(hierarchy_graph), "Hierarchy graph should be complete."


@pytest.mark.asyncio
async def test_hierarchy_annotate(cwd):
    graph = nx.MultiDiGraph()
    graph.graph["cwd"] = cwd.as_posix()
    actual = await Hierarchy().annotate(graph)

    # Load the template graph
    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        expected = nx.readwrite.json_graph.node_link_graph(data)
    for node in expected:  # Add the ID field back in
        expected.nodes[node]["id"] = node

    assert set(actual.nodes) == set(expected.nodes), "Nodes are not equal"
    assert set(actual.edges) == set(expected.edges), "Edges are not equal"
