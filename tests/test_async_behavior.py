import asyncio
import time
from unittest.mock import patch
from pathlib import Path
import pytest

from ragdaemon.generate_graph import generate_pseudo_call_graph

# Mock function to simulate delay
async def mock_get_pseudo_call_graph_for_file(file, graph, cwd, graph_cache={}):
    await asyncio.sleep(.1)
    return {'nodes': [], 'edges': []}

@pytest.mark.asyncio
async def test_generate_pseudo_call_graph_async_behavior():
    sample_dir = Path(__file__).parent / 'sample'
    with patch('ragdaemon.generate_graph.get_pseudo_call_graph_for_file', side_effect=mock_get_pseudo_call_graph_for_file):
        start_time = time.time()
        await generate_pseudo_call_graph(sample_dir)
        total_time = time.time() - start_time

    # If the function is truly asynchronous, total_time should be significantly less than 3 seconds
    assert total_time < .3, "The generate_pseudo_call_graph function does not behave asynchronously as expected."
