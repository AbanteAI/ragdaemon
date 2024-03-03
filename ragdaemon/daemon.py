import json
from pathlib import Path
from typing import Optional

import networkx as nx

from ragdaemon.annotators import annotators_map
from ragdaemon.database import get_db, query_graph
from ragdaemon.llm import token_counter
from ragdaemon.render_context import add_id_to_context, render_context_message


class Daemon:
    """Build and maintain a searchable knowledge graph of codebase."""

    def __init__(
        self,
        cwd: Path,
        annotators: Optional[dict[str, dict]] = None,
        verbose: bool = False,
    ):
        self.cwd = cwd
        self.verbose = verbose

        # Load or setup db
        count = get_db(Path(self.cwd)).count()
        if self.verbose:
            print(f"Initialized database with {count} records.")

        # Load or initialize graph
        self.graph_path = self.cwd / ".ragdaemon" / "graph.json"
        self.graph_path.parent.mkdir(exist_ok=True)
        if self.graph_path.exists():
            self.load()
        else:
            self.graph = nx.MultiDiGraph()
            self.graph.graph["cwd"] = str(self.cwd)
            if self.verbose:
                print(f"Initialized empty graph.")

        if annotators is None:
            annotators = {
                "hierarchy": {},
                "chunker": {"chunk_extensions": [".py", ".js", ".ts"]},
            }
        if self.verbose:
            print(f"Initializing annotators: {list(annotators.keys())}...")
        self.pipeline = {
            ann: annotators_map[ann](**kwargs, verbose=self.verbose)
            for ann, kwargs in annotators.items()
        }

    def save(self):
        """Saves the graph to disk."""
        data = nx.readwrite.json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=4)
        if self.verbose:
            print(f"Saved updated graph to {self.graph_path}")

    def load(self):
        """Load the graph from disk."""
        with open(self.graph_path, "r") as f:
            data = json.load(f)
            self.graph = nx.readwrite.json_graph.node_link_graph(data)

    async def update(self, refresh=False):
        """Iteratively build the knowledge graph"""
        _graph = self.graph.copy()
        self.graph.graph["refreshing"] = True
        for annotator in self.pipeline.values():
            if refresh or not annotator.is_complete(_graph):
                _graph = await annotator.annotate(_graph, refresh=refresh)
        self.graph = _graph
        self.save()

    def search(self, query: str, n: Optional[int] = None) -> list[dict]:
        """Return a sorted list of nodes that match the query."""
        return query_graph(query, self.graph, n=n)

    def get_context_message(
        self,
        query: str,
        include: list[str] = [],
        max_tokens: int = 8000,
        auto_tokens: int = 2000,
    ) -> str:
        """
        Args:
            query: The search query to match context for
            include: List of node refs (path/to/file:line_start-line_end) to include automatically
            max_tokens: The maximum number of tokens for the context message
            auto_tokens: Auto-selected nodes to add in addition to include
        """
        context = {}
        for id in include:
            context = add_id_to_context(
                self.graph, id, context, tags=["user-included"], verbose=self.verbose
            )
        include_context_message = render_context_message(context)
        include_tokens = token_counter(include_context_message)
        if include_tokens >= max_tokens:
            return include_context_message

        full_context_message = include_context_message
        auto_tokens = min(auto_tokens, max_tokens - include_tokens)
        results = self.search(query)
        for i, node in enumerate(results):
            id = node["path"]
            context = add_id_to_context(
                self.graph, id, context, tags=["search-result"], verbose=self.verbose
            )
            next_context_message = render_context_message(context)
            next_tokens = token_counter(next_context_message)
            if (next_tokens - include_tokens) > auto_tokens:
                return full_context_message
            full_context_message = next_context_message
        return full_context_message
