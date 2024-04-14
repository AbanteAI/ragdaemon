import json
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import networkx as nx
from networkx.readwrite import json_graph
import pytest

from ragdaemon.annotators import Chunker, ChunkerLLM
from ragdaemon.daemon import Daemon


def test_chunker_is_complete(cwd, mock_db):
    chunker = Chunker()

    empty_graph = nx.MultiDiGraph()
    assert chunker.is_complete(empty_graph, mock_db), "Empty graph is complete."

    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = json_graph.node_link_graph(data)
    hierarchy_graph = cast(nx.MultiDiGraph, hierarchy_graph)
    assert not chunker.is_complete(
        hierarchy_graph, mock_db
    ), "Hierarchy graph should not be complete."

    incomplete_graph = hierarchy_graph.copy()
    first_node = list(incomplete_graph.nodes)[0]
    incomplete_graph.nodes[first_node]["chunks"] = []
    assert not chunker.is_complete(
        incomplete_graph, mock_db
    ), "Incomplete graph should not be complete"

    for node, data in incomplete_graph.nodes(data=True):
        assert data, f"Node {node} is missing data"
        if data["type"] == "file":
            data["chunks"] = []
    assert chunker.is_complete(
        incomplete_graph, mock_db
    ), "Empty chunks should be complete"

    with open("tests/data/chunker_graph.json", "r") as f:
        data = json.load(f)
        chunker_graph = json_graph.node_link_graph(data)
    chunker_graph = cast(nx.MultiDiGraph, chunker_graph)
    assert chunker.is_complete(
        chunker_graph, mock_db
    ), "Chunker graph should be complete."


@pytest.mark.asyncio
async def test_chunker_llm_annotate(cwd, mock_get_llm_response, mock_db):
    daemon = Daemon(
        cwd=cwd,
        annotators={"hierarchy": {}},
        graph_path=(Path.cwd() / "tests/data/hierarchy_graph.json"),
    )
    chunker = ChunkerLLM(spice_client=AsyncMock())
    actual = await chunker.annotate(daemon.graph, mock_db)

    for node, data in actual.nodes(data=True):
        assert data, f"Node {node} is missing data"
        if data["type"] == "file" and Path(node).suffix in chunker.chunk_extensions:
            assert "chunks" in data, f"File {node} is missing chunks"
