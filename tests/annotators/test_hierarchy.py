import json

from networkx.readwrite import json_graph
import pytest

from ragdaemon.annotators.hierarchy import Hierarchy
from ragdaemon.graph import KnowledgeGraph


def test_hierarchy_is_complete(cwd, io, mock_db):
    empty_graph = KnowledgeGraph()
    empty_graph.graph["cwd"] = cwd.as_posix()
    hierarchy = Hierarchy(io)

    assert not hierarchy.is_complete(
        empty_graph, mock_db
    ), "Empty graph should not be complete."
    incomplete_graph = empty_graph.copy()
    path_str = cwd.as_posix()
    record = {"id": path_str, "type": "directory", "ref": path_str}
    incomplete_graph.add_node(path_str, **record)
    assert not hierarchy.is_complete(
        incomplete_graph, mock_db
    ), "Incomplete graph should not be complete"


@pytest.mark.asyncio
async def test_hierarchy_annotate(cwd, io, mock_db):
    graph = KnowledgeGraph()
    graph.graph["cwd"] = cwd.as_posix()
    hierarchy = Hierarchy(io)
    actual = await hierarchy.annotate(graph, mock_db)

    # Load the template graph
    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        expected = json_graph.node_link_graph(data)
    for node in expected:  # Add the ID field back in
        expected.nodes[node]["id"] = node

    assert set(actual.nodes) == set(expected.nodes), "Nodes are not equal"
    assert set(actual.edges) == set(expected.edges), "Edges are not equal"

    assert hierarchy.is_complete(actual, mock_db), "Graph should be complete"
