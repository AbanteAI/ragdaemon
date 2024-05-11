import asyncio
import json
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from networkx.readwrite import json_graph
from spice import Spice
from spice.models import Model, TextModel
from spice.spice import get_model_from_name

from ragdaemon.annotators import annotators_map
from ragdaemon.context import ContextBuilder
from ragdaemon.database import DEFAULT_EMBEDDING_MODEL, Database, get_db
from ragdaemon.errors import RagdaemonError
from ragdaemon.get_paths import get_paths_for_directory
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.locate import locate
from ragdaemon.utils import DEFAULT_COMPLETION_MODEL, mentat_dir_path


def default_annotators():
    return {
        "hierarchy": {},
        "chunker_line": {"lines_per_chunk": 30},
        "diff": {},
    }


class Daemon:
    """Build and maintain a searchable knowledge graph of codebase."""

    graph: KnowledgeGraph
    _db: Database

    def __init__(
        self,
        cwd: Path,
        annotators: Optional[dict[str, dict]] = None,
        verbose: bool = False,
        graph_path: Optional[Path] = None,
        spice_client: Optional[Spice] = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
        provider: Optional[str] = None,
    ):
        self.cwd = cwd
        self.verbose = verbose
        if graph_path is not None:
            self.graph_path = (cwd / graph_path).resolve()
        else:
            self.graph_path = (
                mentat_dir_path / "ragdaemon" / f"ragdaemon-{self.cwd.name}.json"
            )
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        if spice_client is None:
            logging_dir = mentat_dir_path / "ragdaemon" / "spice_logs"
            logging_dir.mkdir(parents=True, exist_ok=True)
            spice_client = Spice(
                default_text_model=DEFAULT_COMPLETION_MODEL,
                default_embeddings_model=model,
                logging_dir=mentat_dir_path / "ragdaemon" / "spice_logs",
            )
        self.spice_client = spice_client
        self.spice_client.load_dir(Path(__file__).parent / "prompts")
        self.embedding_model = model
        self.embedding_provider = provider

        # Initialize an empty graph
        self.graph = KnowledgeGraph()
        self.graph.graph["cwd"] = self.cwd.as_posix()
        if self.verbose:
            print("Initialized empty graph.")

        annotators = annotators if annotators is not None else default_annotators()
        if self.verbose:
            print(f"Initializing annotators: {list(annotators.keys())}...")
        self.pipeline = {}
        for ann, kwargs in annotators.items():
            self.pipeline[ann] = annotators_map[ann](
                **kwargs,
                verbose=self.verbose,
                spice_client=spice_client,
                pipeline=self.pipeline,
            )

    @property
    def db(self) -> Database:
        if not hasattr(self, "_db"):
            self._db = get_db(
                self.cwd,
                spice_client=self.spice_client,
                embedding_model=self.embedding_model,
                embedding_provider=self.embedding_provider,
                verbose=self.verbose,
            )
        return self._db

    def save(self):
        """Saves the graph to disk."""
        data = json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=4)
        if self.verbose:
            print(f"Saved updated graph to {self.graph_path}")

    async def update(self, refresh=False):
        """Iteratively build the knowledge graph"""
        _graph = self.graph.copy()
        for annotator in self.pipeline.values():
            if refresh or not annotator.is_complete(_graph, self.db):
                _graph = await annotator.annotate(_graph, self.db, refresh=refresh)
        self.graph = _graph
        self.save()

    async def watch(self, interval=2, debounce=5):
        """Calls self.update interval debounce seconds after a file is modified."""
        paths = get_paths_for_directory(self.cwd)
        last_updated = 0
        _update_task = None
        while True:
            await asyncio.sleep(interval)
            paths = get_paths_for_directory(self.cwd)
            _last_updated = max((self.cwd / path).stat().st_mtime for path in paths)
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

    def search(
        self,
        query: str,
        n: Optional[int] = None,
        node_types: Iterable[str] = ("file", "chunk", "diff"),
    ) -> list[dict[str, Any]]:
        """Return a sorted list of nodes that match the query."""
        return self.db.query_graph(query, self.graph, n=n, node_types=node_types)

    def get_document(self, filename: str) -> str:
        checksum = self.graph.nodes[filename]["checksum"]
        document = self.db.get(checksum)["documents"][0]
        return document

    def get_context(
        self,
        query: str,
        context_builder: Optional[ContextBuilder] = None,
        max_tokens: int = 8000,
        auto_tokens: int = 0,
        model: Model | str = DEFAULT_COMPLETION_MODEL,
    ) -> ContextBuilder:
        if context_builder is None:
            context = ContextBuilder(self.graph, self.db, self.verbose)
        else:
            # TODO: Compare graph hashes, reconcile changes
            context = context_builder
        include_context_message = context.render()
        include_tokens = self.spice_client.count_tokens(include_context_message, model)
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
            next_tokens = self.spice_client.count_tokens(next_context_message, model)
            if (next_tokens - include_tokens) > auto_tokens:
                if node["type"] == "diff":
                    context.remove_diff(node["id"])
                else:
                    context.remove_ref(node["ref"])
                break
        return context

    async def locate(
        self,
        query: str,
        instruction: Optional[str] = None,
        revise: bool = True,
        model: Model | TextModel | str = DEFAULT_COMPLETION_MODEL,
    ) -> list[str]:
        """Use summaries to scan the codebase and return relevant nodes."""
        if "summarizer" not in self.pipeline:
            raise RagdaemonError(f"Summarizer annotator required for locate.")
        if instruction is None:
            instruction = "Return items which are relevant to fulfilling the query."
        if isinstance(model, str):
            model = get_model_from_name(model)
        if not isinstance(model, TextModel):
            raise RagdaemonError(f"Invalid model: {model}")

        edge_type = "hierarchy"
        summary_field_id = "summary"
        return await locate(
            self.graph,
            edge_type,
            summary_field_id,
            self.spice_client,
            instruction,
            query,
            model,
            revise=revise,
        )
