import json

import networkx as nx
import pytest

from ragdaemon.daemon import Daemon
from ragdaemon.annotators.chunker import Chunker


def test_chunker_is_complete(cwd):
    chunker = Chunker()

    empty_graph = nx.MultiDiGraph()
    assert chunker.is_complete(empty_graph), "Empty graph is complete."

    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert not chunker.is_complete(
        hierarchy_graph
    ), "Hierarchy graph should not be complete."

    incomplete_graph = hierarchy_graph.copy()
    first_node = list(incomplete_graph.nodes)[0]
    incomplete_graph.nodes[first_node]["chunks"] = []
    assert not chunker.is_complete(
        incomplete_graph
    ), "Incomplete graph should not be complete"

    for _, data in incomplete_graph.nodes(data=True):
        if data["type"] == "file":
            data["chunks"] = []
    assert chunker.is_complete(incomplete_graph), "Empty chunks should be complete"

    with open("tests/data/chunker_graph.json", "r") as f:
        data = json.load(f)
        chunker_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert chunker.is_complete(chunker_graph), "Chunker graph should be complete."


@pytest.mark.asyncio
async def test_chunker_annotate(cwd, mock_get_llm_response):
    daemon = Daemon(
        cwd=cwd, 
        annotators={"hierarchy": {}}, 
        graph_path="tests/data/hierarchy_graph.json"
    )
    actual = await Chunker().annotate(daemon.graph)

    for node, data in actual.nodes(data=True):
        if data["type"] == "file":
            assert "chunks" in data, f"File {node} is missing chunks"
