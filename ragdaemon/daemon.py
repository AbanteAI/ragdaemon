import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from ragdaemon.annotators import Annotator, annotators_map
from ragdaemon.context import ContextBuilder
from ragdaemon.database import get_db, query_graph
from ragdaemon.llm import completion_model, token_counter
from ragdaemon.utils import get_non_gitignored_files


def default_annotators():
    return {
        "hierarchy": {},
        "chunker": {"chunk_extensions": [".py", ".js", ".ts"]},
        "diff": {},
    }


class Daemon:
    """Build and maintain a searchable knowledge graph of codebase."""

    graph: nx.MultiDiGraph

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
            self.graph.graph["cwd"] = self.cwd.as_posix()
            if self.verbose:
                print("Initialized empty graph.")

        annotators = annotators if annotators is not None else default_annotators()
        if self.verbose:
            print(f"Initializing annotators: {list(annotators.keys())}...")
        if "chunker" in annotators and completion_model is None:
            if self.verbose:
                print("No completion model found, disabling chunker.")
            del annotators["chunker"]
        self.pipeline: dict[str, Annotator] = {
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
        self.graph.graph["cwd"] = self.cwd.as_posix()

    async def update(self, refresh=False):
        """Iteratively build the knowledge graph"""
        _graph = self.graph.copy()
        self.graph.graph["refreshing"] = True
        for annotator in self.pipeline.values():
            if refresh or not annotator.is_complete(_graph):
                _graph = await annotator.annotate(_graph, refresh=refresh)
        self.graph = _graph
        self.save()

    async def watch(self, interval=2, debounce=5):
        """Calls self.update interval debounce seconds after a file is modified."""
        git_paths = get_non_gitignored_files(self.cwd)
        last_updated = 0
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

    def search(self, query: str, n: Optional[int] = None) -> list[dict[str, Any]]:
        """Return a sorted list of nodes that match the query."""
        return query_graph(query, self.graph, n=n)

    def get_context(
        self,
        query: str,
        context_builder: Optional[ContextBuilder] = None,
        max_tokens: int = 8000,
        auto_tokens: int = 0,
    ):
        if context_builder is None:
            context = ContextBuilder(self.graph, self.verbose)
        else:
            # TODO: Compare graph hashes, reconcile changes
            context = context_builder
        include_context_message = context.render()
        include_tokens = token_counter(include_context_message)
        if not auto_tokens or include_tokens >= max_tokens:
            return context

        auto_tokens = min(auto_tokens, max_tokens - include_tokens)
        results = self.search(query)
        for node in results:
            if node["type"] == "diff":
                context.add_diff(node["id"])
            else:
                context.add_ref(node["ref"], tags=["search-result"])
            next_context_message = context.render()
            next_tokens = token_counter(next_context_message)
            if (next_tokens - include_tokens) > auto_tokens:
                if node["type"] == "diff":
                    context.remove_diff(node["id"])
                else:
                    context.remove_ref(node["ref"])
                break
        return context
