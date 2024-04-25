from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ragdaemon.annotators import Chunker, ChunkerLLM
from ragdaemon.daemon import Daemon
from ragdaemon.graph import KnowledgeGraph


@pytest.fixture
def mock_get_llm_response():
    with patch(
        "ragdaemon.annotators.chunker_llm.ChunkerLLM.get_llm_response",
        return_value={"chunks": []},
    ) as mock:
        yield mock


def test_chunker_is_complete(cwd, mock_db):
    chunker = Chunker()

    empty_graph = KnowledgeGraph()
    assert chunker.is_complete(empty_graph, mock_db), "Empty graph is complete."

    hierarchy_graph = KnowledgeGraph.load("tests/data/hierarchy_graph.json")
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

    chunker_graph = KnowledgeGraph.load("tests/data/chunker_graph.json")
    assert chunker.is_complete(
        chunker_graph, mock_db
    ), "Chunker graph should be complete."


@pytest.mark.asyncio
async def test_chunker_llm_annotate(cwd, mock_get_llm_response, mock_db):
    daemon = Daemon(
        cwd=cwd,
        annotators={"hierarchy": {}},
    )
    chunker = ChunkerLLM(spice_client=AsyncMock())
    actual = await chunker.annotate(daemon.graph, mock_db)

    for node, data in actual.nodes(data=True):
        assert data, f"Node {node} is missing data"
        if data["type"] == "file" and Path(node).suffix in chunker.chunk_extensions:
            assert "chunks" in data, f"File {node} is missing chunks"
