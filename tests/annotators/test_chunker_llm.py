from pathlib import Path

import pytest

from ragdaemon.annotators.chunker_llm import ChunkerLLM
from ragdaemon.daemon import Daemon


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


@pytest.mark.skip(reason="This test requires calling an API")
@pytest.mark.asyncio
async def test_chunker_llm_edge_cases(cwd, expected_chunks):
    # NOTE: TO RUN THIS YOU HAVE TO COMMENT_OUT tests/conftest.py/mock_openai_api_key
    daemon = Daemon(cwd, annotators={"hierarchy": {}})
    chunker = ChunkerLLM(spice_client=daemon.spice_client)

    # One example with all the edge cases (when batch_size = 10 lines):
    # - First batch ends mid-class, so second batch needs 'call path'
    # - Second batch ends mid-function, third batch needs to pickup where it left off
    # - Third batch is all inside one function, so needs to pass call forward.
    text = Path("tests/data/hard_to_chunk.txt").read_text()
    document = f"src/calculator.py\n{text}"
    actual_chunks = await chunker.chunk_document(document, batch_size=10)

    print(actual_chunks)

    assert len(actual_chunks) == len(expected_chunks)
    actual_chunks = sorted(actual_chunks, key=lambda x: x["ref"])
    expected_chunks = sorted(expected_chunks, key=lambda x: x["ref"])
    for actual, expected in zip(actual_chunks, expected_chunks):
        assert actual == expected
