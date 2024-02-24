import json

import networkx as nx
import pytest

from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy


def test_hierarchy_is_complete(cwd):
    layout_hierarchy = LayoutHierarchy(cwd)
    
    empty_graph = nx.MultiDiGraph()
    assert layout_hierarchy.is_complete(empty_graph), "Empty graph is complete."

    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert not layout_hierarchy.is_complete(hierarchy_graph), "Hierarchy graph should not be complete."
    incomplete_graph = hierarchy_graph.copy()
    first_node = list(incomplete_graph.nodes)[0]
    incomplete_graph.nodes[first_node]["layout"] = {"hierarchy": {"x": 0, "y": 0, "z": 0}}
    assert not layout_hierarchy.is_complete(incomplete_graph), "Incomplete graph should not be complete"

@pytest.mark.asyncio
async def test_hierarchy_annotate(cwd):
    layout_hierarchy = LayoutHierarchy(cwd)

    with open("tests/annotators/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)

    actual = await layout_hierarchy.annotate(hierarchy_graph)
    for _, data in actual.nodes(data=True):
        assert "layout" in data, "Layout data is missing"
        assert "hierarchy" in data["layout"], "Hierarchy layout data is missing"
        for axis in ["x", "y", "z"]:
            assert isinstance(data["layout"]["hierarchy"][axis], (int, float)), f"Axis {axis} is not a number"
