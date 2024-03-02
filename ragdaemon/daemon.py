import json
from pathlib import Path

import networkx as nx

from ragdaemon.annotators import Hierarchy, Chunker, LayoutHierarchy
from ragdaemon.database import get_db, query_graph
from ragdaemon.llm import token_counter


class Daemon:
    """Build and maintain a searchable knowledge graph of codebase."""

    def __init__(self, cwd: Path):
        self.cwd = cwd

        # Load or setup db
        count = get_db(Path(self.cwd)).count()
        print(f"Initialized database with {count} records.")

        # Load or initialize graph
        self.graph_path = self.cwd / ".ragdaemon" / "graph.json"
        self.graph_path.parent.mkdir(exist_ok=True)
        if self.graph_path.exists():
            self.load()
        else:
            self.graph = nx.MultiDiGraph()
            self.graph.graph["cwd"] = str(cwd)
            print(f"Initialized empty graph.")

        self.pipeline = [
            Hierarchy(),
            Chunker(),
            LayoutHierarchy(),
        ]

    def save(self):
        """Saves the graph to disk."""
        data = nx.readwrite.json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"refreshed knowledge graph saved to {self.graph_path}")

    def load(self):
        """Load the graph from disk."""
        with open(self.graph_path, "r") as f:
            data = json.load(f)
            self.graph = nx.readwrite.json_graph.node_link_graph(data)
                
    async def refresh(self):
        """Iteratively build the knowledge graph"""
        _graph = self.graph.copy()
        self.graph.graph["refreshing"] = True
        for annotator in self.pipeline:
            if not annotator.is_complete(_graph):
                _graph = await annotator.annotate(_graph)
        self.graph = _graph
        self.save()

    def search(self, query: str) -> list[dict]:
        """Return a sorted list of nodes that match the query."""
        return query_graph(query, self.graph)
    
    def render_context_message(self, nodes: list[dict]) -> str:
        """Return a formatted context message for the given nodes."""
        output = ""
        for node in nodes:
            if output:
                output += "\n"
            tags = "" if "tags" not in node else f" ({', '.join(node['tags'])})"
            lines = "\n".join(f"{i+1}: {line}" for i, line in enumerate(node["document"].splitlines()))
            output += f"{node['id']}{tags}\n{lines}"
        return output

    def get_context_message(
        self, 
        query: str, 
        include: list[str] = [], 
        max_tokens: int = 8000, 
        auto_tokens: int = 2000,
    ) -> str:
        """Return formatted context for the given query."""
        selected = []
        for id in include:
            if ":" in id:
                id = id.split(":")[0]  # TODO: support line numbers
            if id in self.graph:
                selected.append({**self.graph.nodes[id], "tags": ["user-included"]})
            else:
                print(f"Warning: {id} not found in results.")
        include_context_message = self.render_context_message(selected)
        include_tokens = token_counter(include_context_message)
        if include_tokens >= max_tokens:
            return include_context_message

        auto_tokens = min(auto_tokens, max_tokens - include_tokens)
        results = self.search(query)
        while query and results:
            node_id = results.pop(0)
            was_included = any(node_id == node["id"] for node in selected)
            if was_included:
                node = next(node for node in selected if node["id"] == node_id)
                node["tags"].append("auto-included")
            else:
                node = {**self.graph.nodes[node_id], "tags": ["embedding-similarity"]}
            next_context_message = self.render_context_message(selected + [node])
            next_tokens = token_counter(next_context_message)
            if (next_tokens - include_tokens) > auto_tokens:
                break
