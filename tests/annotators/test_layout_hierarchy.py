import pytest

from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy
from ragdaemon.graph import KnowledgeGraph


def test_layout_hierarchy_is_complete(cwd, mock_db):
    layout_hierarchy = LayoutHierarchy()

    empty_graph = KnowledgeGraph()
    assert layout_hierarchy.is_complete(
        empty_graph, mock_db
    ), "Empty graph is complete."

    hierarchy_graph = KnowledgeGraph.load("tests/data/hierarchy_graph.json")
    assert not layout_hierarchy.is_complete(
        hierarchy_graph, mock_db
    ), "Hierarchy graph should not be complete."

    incomplete_graph = hierarchy_graph.copy()
    first_node = list(incomplete_graph.nodes)[0]
    incomplete_graph.nodes[first_node]["layout"] = {
        "hierarchy": {"x": 0, "y": 0, "z": 0}
    }
    assert not layout_hierarchy.is_complete(
        incomplete_graph, mock_db
    ), "Incomplete graph should not be complete"

    layout_hierarchy_graph = KnowledgeGraph.load(
        "tests/data/layout_hierarchy_graph.json"
    )
    assert layout_hierarchy.is_complete(
        layout_hierarchy_graph, mock_db
    ), "Layout hierarchy graph should be complete."


@pytest.mark.asyncio
async def test_layout_hierarchy_annotate(cwd, mock_db):
    hierarchy_graph = KnowledgeGraph.load("tests/data/hierarchy_graph.json")
    actual = await LayoutHierarchy().annotate(hierarchy_graph, mock_db)

    all_coordinates = set()
    for node, data in actual.nodes(data=True):
        assert data, f"Node {node} is missing data"
        coordinates = data.get("layout", {}).get("hierarchy", {})
        assert coordinates, f"Node {node} is missing hierarchy layout"
        all_coordinates.add((coordinates["x"], coordinates["y"], coordinates["z"]))
    assert (
        len(all_coordinates) == actual.number_of_nodes()
    ), "Coordinates are not unique"
