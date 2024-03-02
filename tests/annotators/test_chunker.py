import json

import networkx as nx
import pytest

from ragdaemon.annotators.chunker import Chunker, get_file_chunk_data, add_file_chunks_to_graph


def test_get_file_chunk_data():
    pass


def test_add_file_chunks_to_graph():
    pass


def test_chunker_is_complete(cwd):
    chunker = Chunker()
    
    empty_graph = nx.MultiDiGraph()
    assert chunker.is_complete(empty_graph), "Empty graph is complete."

    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert not chunker.is_complete(hierarchy_graph), "Hierarchy graph should not be complete."
    
    incomplete_graph = hierarchy_graph.copy()
    first_node = list(incomplete_graph.nodes)[0]
    incomplete_graph.nodes[first_node]["chunks"] = []
    assert not chunker.is_complete(incomplete_graph), "Incomplete graph should not be complete"

    for _, data in incomplete_graph.nodes(data=True):
        if data["type"] == "file":
            data["chunks"] = []
    assert chunker.is_complete(incomplete_graph), "Empty chunks should be complete"

    with open("tests/annotators/data/chunker_graph.json", "r") as f:
        data = json.load(f)
        chunker_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert chunker.is_complete(chunker_graph), "Chunker graph should be complete."


@pytest.mark.asyncio
async def test_chunker_annotate(cwd, mock_get_llm_response):
    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    actual = await Chunker().annotate(hierarchy_graph)
    
    for node, data in actual.nodes(data=True):
        if data["type"] == "file":
            assert "chunks" in data, f"File {node} is missing chunks"
