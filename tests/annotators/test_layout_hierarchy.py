import json

import networkx as nx
import pytest

from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy


def test_layout_hierarchy_is_complete(cwd):
    layout_hierarchy = LayoutHierarchy()

    empty_graph = nx.MultiDiGraph()
    assert layout_hierarchy.is_complete(empty_graph), "Empty graph is complete."

    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert not layout_hierarchy.is_complete(
        hierarchy_graph
    ), "Hierarchy graph should not be complete."

    incomplete_graph = hierarchy_graph.copy()
    first_node = list(incomplete_graph.nodes)[0]
    incomplete_graph.nodes[first_node]["layout"] = {
        "hierarchy": {"x": 0, "y": 0, "z": 0}
    }
    assert not layout_hierarchy.is_complete(
        incomplete_graph
    ), "Incomplete graph should not be complete"

    with open("tests/data/layout_hierarchy_graph.json", "r") as f:
        data = json.load(f)
        layout_hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    assert layout_hierarchy.is_complete(
        layout_hierarchy_graph
    ), "Layout hierarchy graph should be complete."


@pytest.mark.asyncio
async def test_layout_hierarchy_annotate(cwd):
    with open("tests/data/hierarchy_graph.json", "r") as f:
        data = json.load(f)
        hierarchy_graph = nx.readwrite.json_graph.node_link_graph(data)
    actual = await LayoutHierarchy().annotate(hierarchy_graph)

    all_coordinates = set()
    for node, data in actual.nodes(data=True):
        coordinates = data.get("layout", {}).get("hierarchy", {})
        assert coordinates, f"Node {node} is missing hierarchy layout"
        all_coordinates.add((coordinates["x"], coordinates["y"], coordinates["z"]))
    assert (
        len(all_coordinates) == actual.number_of_nodes()
    ), "Coordinates are not unique"
