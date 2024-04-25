from unittest.mock import AsyncMock, patch

import pytest

from ragdaemon.annotators import Summarizer
from ragdaemon.daemon import Daemon


@pytest.fixture
def mock_get_llm_response():
    with patch(
        "ragdaemon.annotators.summarizer.Summarizer.get_llm_response",
        return_value="summary of",
    ) as mock:
        yield mock


@pytest.mark.asyncio
async def test_summarizer_annotate(cwd, mock_get_llm_response):
    daemon = Daemon(
        cwd=cwd,
        annotators={"hierarchy": {}},
    )
    await daemon.update(refresh=True)
    summarizer = Summarizer(spice_client=AsyncMock())
    actual = await summarizer.annotate(daemon.graph, daemon.db)
    for _, data in actual.nodes(data=True):
        if data.get("checksum") is not None:
            assert data.get("summary") == "summary of"
