import json
from pathlib import Path

import pytest
import networkx as nx

from ragdaemon.annotators.hierarchy import get_active_checksums, Hierarchy


def test_get_active_checksums(cwd):
    checksums = get_active_checksums(cwd)
    assert isinstance(checksums, dict), "Checksums is not a dict"
    assert all(isinstance(k, Path) for k in checksums), "Keys are not all Paths"
    assert all(isinstance(v, str) for v in checksums.values()), "Values are not all strings"

    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    expected = {(node, data["checksum"]) for node, data in hierarchy_graph.nodes(data=True) if "checksum" in data}
    actual = {(str(path), checksum) for path, checksum in checksums.items()}
    assert actual == expected, "Checksums are not equal"


def test_hierarchy_is_complete(cwd):
    empty_graph = nx.MultiDiGraph()
    empty_graph.graph["cwd"] = str(cwd)
    hierarchy = Hierarchy()

    assert not hierarchy.is_complete(empty_graph), "Empty graph should not be complete."
    incomplete_graph = empty_graph.copy()
    incomplete_graph.add_node(str(cwd), path=str(cwd), type="directory", id=str(cwd))
    assert not hierarchy.is_complete(incomplete_graph), "Incomplete graph should not be complete"

    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert hierarchy.is_complete(hierarchy_graph), "Hierarchy graph should be complete."


@pytest.mark.asyncio
async def test_hierarchy_annotate(cwd):
    graph = nx.MultiDiGraph()
    graph.graph["cwd"] = str(cwd)
    actual = await Hierarchy().annotate(graph)

    # Load the template graph
    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        expected = nx.readwrite.json_graph.node_link_graph(data)
    for node in expected:  # Add the ID field back in
        expected.nodes[node]["id"] = node

    assert set(actual.nodes) == set(expected.nodes), "Nodes are not equal"
    assert set(actual.edges) == set(expected.edges), "Edges are not equal"
