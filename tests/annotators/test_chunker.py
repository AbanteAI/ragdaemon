from pathlib import Path

import pytest

from ragdaemon.annotators import Chunker
from ragdaemon.annotators.chunker.chunk_llm import chunk_document as chunk_llm
from ragdaemon.annotators.chunker.chunk_astroid import chunk_document as chunk_astroid
from ragdaemon.daemon import Daemon
from ragdaemon.graph import KnowledgeGraph


def test_chunker_is_complete(io, mock_db):
    chunker = Chunker(io)

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


@pytest.fixture
def expected_chunks():
    return [
        {"id": "src/calculator.py:BASE", "ref": "src/calculator.py:1-4,29,42-45"},
        {
            "id": "src/calculator.py:Calculator",
            "ref": "src/calculator.py:5,10,13,16,19",
        },
        {"id": "src/calculator.py:Calculator.__init__", "ref": "src/calculator.py:6-9"},
        {
            "id": "src/calculator.py:Calculator.add_numbers",
            "ref": "src/calculator.py:11-12",
        },
        {
            "id": "src/calculator.py:Calculator.subtract_numbers",
            "ref": "src/calculator.py:14-15",
        },
        {
            "id": "src/calculator.py:Calculator.exp_numbers",
            "ref": "src/calculator.py:17-18",
        },
        {"id": "src/calculator.py:Calculator.call", "ref": "src/calculator.py:20-28"},
        {"id": "src/calculator.py:main", "ref": "src/calculator.py:30-41"},
    ]


@pytest.mark.asyncio
async def test_chunker_astroid(expected_chunks):
    text = Path("tests/data/hard_to_chunk.txt").read_text()
    document = f"src/calculator.py\n{text}"
    actual_chunks = await chunk_astroid(document)

    assert len(actual_chunks) == len(expected_chunks)
    actual_chunks = sorted(actual_chunks, key=lambda x: x["ref"])
    expected_chunks = sorted(expected_chunks, key=lambda x: x["ref"])
    for actual, expected in zip(actual_chunks, expected_chunks):
        assert actual == expected


@pytest.mark.skip(reason="This test requires calling an API")
@pytest.mark.asyncio
async def test_chunk_llm(cwd, expected_chunks):
    # NOTE: TO RUN THIS YOU HAVE TO COMMENT_OUT tests/conftest.py/mock_openai_api_key
    daemon = Daemon(cwd, annotators={"hierarchy": {}})

    # One example with all the edge cases (when batch_size = 10 lines):
    # - First batch ends mid-class, so second batch needs 'call path'
    # - Second batch ends mid-function, third batch needs to pickup where it left off
    # - Third batch is all inside one function, so needs to pass call forward.
    text = Path("tests/data/hard_to_chunk.txt").read_text()
    document = f"src/calculator.py\n{text}"
    actual_chunks = await chunk_llm(
        spice_client=daemon.spice_client,
        document=document,
        batch_size=10,
        verbose=2,
    )

    print(actual_chunks)

    assert len(actual_chunks) == len(expected_chunks)
    actual_chunks = sorted(actual_chunks, key=lambda x: x["ref"])
    expected_chunks = sorted(expected_chunks, key=lambda x: x["ref"])
    for actual, expected in zip(actual_chunks, expected_chunks):
        assert actual == expected
