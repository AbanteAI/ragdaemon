import time
import asyncio
import json
from pathlib import Path
from typing import Optional

import networkx as nx

from ragdaemon.annotators import annotators_map
from ragdaemon.database import get_db, query_graph
from ragdaemon.llm import token_counter
from ragdaemon.context import ContextBuilder
from ragdaemon.utils import get_non_gitignored_files


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

    async def watch(self, refresh=False, interval=2, debounce=5):
        """Calls self.update interval seconds after a file is modified. """
        await self.update(refresh)  # Initial update
        git_paths = get_non_gitignored_files(self.cwd)
        last_updated = max((self.cwd / path).stat().st_mtime for path in git_paths)
        _update_task = None
        while True:
            await asyncio.sleep(interval)
            git_paths = get_non_gitignored_files(self.cwd)
            _last_updated = max((self.cwd / path).stat().st_mtime for path in git_paths)
            if (
                _last_updated > last_updated
                and (time.time() - _last_updated) > debounce
            ):
                if _update_task is not None:
                    try:
                        _update_task.cancel()
                        await _update_task
                    except asyncio.CancelledError:
                        pass
                last_updated = _last_updated
                _update_task = asyncio.create_task(self.update())

    def search(self, query: str, n: Optional[int] = None) -> list[dict]:
        """Return a sorted list of nodes that match the query."""
        return query_graph(query, self.graph, n=n)
    
    def get_context(
        self,
        query: str,
        include: list[str] = [],
        max_tokens: int = 8000,
        auto_tokens: int = 2000,
    ):
        context = ContextBuilder(self.graph, self.verbose)
        for ref in include:
            context.add(ref, tags=["user-included"])
        include_context_message = context.render()
        include_tokens = token_counter(include_context_message)
        if include_tokens >= max_tokens:
            return include_context_message

        auto_tokens = min(auto_tokens, max_tokens - include_tokens)
        results = self.search(query)
        for node in results:
            context.add(node["ref"], tags=["search-result"])
            next_context_message = context.render()
            next_tokens = token_counter(next_context_message)
            if (next_tokens - include_tokens) > auto_tokens:
                context.remove(node["ref"])
                break
        return context

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
        context = self.get_context(query, include, max_tokens, auto_tokens)
        return context.render()
