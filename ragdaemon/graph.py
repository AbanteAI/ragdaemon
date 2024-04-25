import json
from typing import Any, cast, TypedDict, Literal, Optional

import networkx as nx
from networkx.readwrite import json_graph


class NodeMetadata(TypedDict):
    id: Optional[str]  # Human-readable path, e.g. `path/to/file:class.method`
    type: Literal["directory", "file", "chunk", "diff"]
    ref: Optional[
        str
    ]  # Used to fetch document: path/to/file:start-end, diff_ref:start-end
    checksum: Optional[str]  # Unique identifier for chroma; sha256 of the document
    active: bool  # Used to filter nodes for search
    chunks: Optional[
        list[dict[str, str]]
    ]  # For files, func/class/method. For diff, by file/hunk
    summary: Optional[str]  # Generated summary of the node


class EdgeMetadata(TypedDict):
    type: Literal["hierarchy", "diff"]


def validate_attrs(attrs: dict[str, Any], type: Literal["node", "edge"]):
    if type == "node":
        metadata = NodeMetadata
    elif type == "edge":
        metadata = EdgeMetadata
    try:
        metadata(**attrs)
    except TypeError as e:
        raise TypeError(f"Invalid attributes for {type}: {e}")


class GraphMetadata(TypedDict):
    cwd: str  # Current working directory
    files_checksum: str  # Hash of all active files in cwd


class KnowledgeGraph(nx.MultiDiGraph):
    graph: GraphMetadata

    @classmethod
    def load(cls, path: str):
        with open(path, "r") as f:
            data = json.load(f)
            graph = json_graph.node_link_graph(data)
            return cls(graph)

    def copy(self, *args, **kwargs):
        return cast(KnowledgeGraph, super().copy(*args, **kwargs))

    def add_node(self, node_for_adding: str, **attrs):
        validate_attrs(attrs, "node")
        return super().add_node(node_for_adding, **attrs)

    def add_edge(
        self, u_for_edge: str, v_for_edge: str, key: Optional[str | int] = None, **attrs
    ):
        validate_attrs(attrs, "edge")
        return super().add_edge(u_for_edge, v_for_edge, key, **attrs)
