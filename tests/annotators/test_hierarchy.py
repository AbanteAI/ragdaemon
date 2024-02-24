import json
from pathlib import Path

import pytest
import networkx as nx

from ragdaemon.annotators.hierarchy import Hierarchy


@pytest.fixture
def hierarchy_graph(cwd):
    pass

def test_hierarchy_is_complete(cwd):
    hierarchy = Hierarchy(cwd)
    
    empty_graph = nx.MultiDiGraph()
    assert not hierarchy.is_complete(empty_graph), "Empty graph should not be complete."
    incomplete_graph = empty_graph.copy()
    incomplete_graph.add_node(str(cwd), path=str(cwd), type="directory", id=str(cwd))
    assert not hierarchy.is_complete(incomplete_graph), "Incomplete graph should not be complete"


@pytest.mark.asyncio
async def test_hierarchy_annotate():
    graph = nx.MultiDiGraph()
    cwd = Path("tests/sample")
    hierarchy = Hierarchy(cwd)
    actual = await hierarchy.annotate(graph)

    # Load the template graph
    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        expected = nx.readwrite.json_graph.node_link_graph(data)
    for node in expected:  # Add the ID field back in
        expected.nodes[node]["id"] = node

    assert set(actual.nodes) == set(expected.nodes), "Nodes are not equal"
    for node in actual.nodes:
        assert actual.nodes[node] == expected.nodes[node], f"Node data is not equal: {node}"
    assert set(actual.edges) == set(expected.edges), "Edges are not equal"
    for edge in actual.edges:
        assert actual.edges[edge] == expected.edges[edge], f"Edge data is not equal: {edge}"
