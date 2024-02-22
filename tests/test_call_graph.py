import os
from pathlib import Path

import networkx as nx
import pytest

from ragdaemon.generate_graph import generate_pseudo_call_graph


@pytest.fixture
def change_cwd_to_sample():
    """Fixture to change cwd to sample directory during test."""
    sample_dir = Path(__file__).parent / "sample"
    prev_cwd = Path.cwd()
    os.chdir(sample_dir)
    yield
    os.chdir(prev_cwd)


def test_parse_python_files(change_cwd_to_sample):

    # Initialize the parser and the graph
    G = nx.MultiDiGraph()
    sample_dir = Path(__file__).parent / "sample"
    
    # Parse the files and generate the graph
    G = generate_pseudo_call_graph(sample_dir)

    assert len(G) > 0, "The graph should not be empty."

    main_node = "main.py:main"
    assert main_node in G, f"The graph should contain a node for the `main` function: {main_node}"

    add_node = "src/operations.py:add"
    assert G.has_edge(main_node, add_node), f"The graph should contain an edge from `{main_node}` to `{add_node}`"
