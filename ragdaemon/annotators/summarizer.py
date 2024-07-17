import asyncio
from collections import deque
from typing import List, Optional

from spice import Spice, SpiceMessages
from spice.models import TextModel
from spice.spice import get_model_from_name
from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.context import ContextBuilder
from ragdaemon.database import Database, remove_update_db_duplicates
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.io import IO
from ragdaemon.utils import (
    DEFAULT_COMPLETION_MODEL,
    match_refresh,
    semaphore,
    truncate,
)


def get_leaf_nodes(
    graph: KnowledgeGraph,
    node: str,
    edge_type: str = "hierarchy",
    seen: Optional[set[str]] = None,
) -> list[str]:
    """Return all leaf nodes in the hierarchy rooted at the given node, breadth-first"""
    if seen is None:
        seen = set()
    queue: deque = deque([node])
    leaf_nodes: List[str] = []

    while queue:
        current = queue.popleft()
        if current not in seen:
            seen.add(current)
            children = [
                edge[1]
                for edge in graph.out_edges(current, data=True)
                if edge[-1].get("type") == edge_type
            ]
            if children:
                queue.extend(children)
            else:
                leaf_nodes.append(current)

    return leaf_nodes


def build_filetree(
    graph: KnowledgeGraph,
    target: str,
    current: str = "ROOT",
    prefix: str = "",
    summary_field_id: str = "summary",
) -> list[str]:
    """Return the list of files and summaries for all directories back to the root"""
    filetree = list[str]()
    edges = sorted(graph.out_edges(current, data=True), key=lambda x: x[1])
    for edge in edges:
        if edge[-1].get("type") == "hierarchy":
            child = edge[1]
            line = child
            summary = graph.nodes[child].get(summary_field_id)
            leaf_nodes = len(get_leaf_nodes(graph, child))
            if leaf_nodes > 1:
                line += f" ({leaf_nodes} items)"
            if summary:
                line += " - " + summary
            if child == target:
                line = f"<b>{line}</b>"
            line = prefix + line
            filetree.append(line)
            if (
                target.startswith(child)
                and graph.nodes[child].get("type") == "directory"
            ):
                filetree.extend(build_filetree(graph, target, child, prefix + "  "))
    return filetree


def get_document_and_context(
    node: str,
    graph: KnowledgeGraph,
    io: IO,
    summary_field_id: str = "summary",
    model: Optional[TextModel] = None,
) -> tuple[str, str]:
    """Return the document and type-specific context for a node in the graph."""
    data = graph.nodes[node]
    if not data:
        raise RagdaemonError(f"Node {node} not found in graph")
    checksum = data.get("checksum")
    if not checksum:
        raise RagdaemonError(f"Node {node} has no checksum.")

    if data.get("type") == "directory":
        document = f"Directory: {node}"
    else:
        cb = ContextBuilder(graph, io)
        cb.add_id(node)
        document = cb.render()

    if data.get("type") == "chunk":
        cb = ContextBuilder(graph, io)

        # Parent chunks back to the file
        def get_hierarchical_parents(target: str, cb: ContextBuilder):
            """Recursviely select parent chunks linked by hierarchy edges."""
            for parent in graph.predecessors(target):
                if graph.nodes[parent].get("type") != "chunk":
                    return
                edges = graph.get_edge_data(parent, target)
                for _, data in edges.items():
                    if data.get("type") == "hierarchy":
                        cb.add_id(
                            parent,
                            tags=["chunk context"],
                            summary_field_id=summary_field_id,
                        )
                        get_hierarchical_parents(parent, cb)

        get_hierarchical_parents(node, cb)
        # Call graph neighbors
        callers = [
            edge[0]
            for edge in graph.in_edges(node, data=True)
            if edge[-1].get("type") == "call"
        ]
        callees = [
            edge[1]
            for edge in graph.out_edges(node, data=True)
            if edge[-1].get("type") == "call"
        ]
        if callers or callees:
            for neighbor in set(callers + callees):
                cb.add_id(
                    neighbor, tags=["call graph"], summary_field_id=summary_field_id
                )
        context = cb.render(use_tags=True, remove_whitespace=True)

    elif data.get("type") == "file":
        context = ""
        # Include file tree path to root, siblings + their summaries
        filetree = "\n".join(
            build_filetree(graph, node, summary_field_id=summary_field_id)
        )
        if filetree:
            context += f"<file_tree>\n{filetree}\n</file_tree>\n"

        # Chunks and their summaries
        def get_chunk_summaries(target: str) -> list[str]:
            summaries = list[str]()
            for edge in graph.out_edges(target, data=True):
                if edge[0] == edge[1]:
                    continue
                if edge[-1].get("type") == "hierarchy":
                    child = edge[1]
                    if graph.nodes[child].get("type") == "chunk":
                        summary = graph.nodes[child].get(summary_field_id, "")
                        summaries.append(child + " " + summary)
                        child_summaries = get_chunk_summaries(child)
                        summaries.extend(child_summaries)
            return summaries

        chunk_summaries = "\n".join(get_chunk_summaries(node))
        if chunk_summaries:
            if context:
                context += "\n"
            context += f"<chunk_summaries>\n{chunk_summaries}\n</chunk_summaries>\n"

    elif data.get("type") == "directory":
        filetree = "\n".join(
            build_filetree(graph, node, summary_field_id=summary_field_id)
        )
        if filetree:
            context = f"<file_tree>\n{filetree}\n</file_tree>"
        else:
            context = ""

    else:
        raise RagdaemonError(f"Unsupported type: {data.get('type')}")

    if model is not None and model.context_length is not None:
        prompt_buffer = 0.1
        max_tokens = model.context_length * (1 - prompt_buffer)
        document_tokens = round(max_tokens * 0.8)
        document, _ = truncate(document, model=model, tokens=document_tokens)
        context_tokens = round(max_tokens - Spice().count_tokens(context, model))
        context, _ = truncate(context, model=model, tokens=context_tokens)

    return document, context


class Summarizer(Annotator):
    name = "summarizer"
    summary_field_id = "summary"
    checksum_field_id = "summary_checksum"

    def __init__(
        self,
        *args,
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        summarize_nodes: list[str] = ["file", "chunk", "directory"],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if isinstance(model, str):
            _model = get_model_from_name(model)
            if not isinstance(_model, TextModel):
                raise RagdaemonError(f"Not a text model: {model}")
            model = _model
        self.model = model
        self.summarize_nodes = summarize_nodes

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") not in self.summarize_nodes:
                continue
            if data.get("checksum") is None:
                raise RagdaemonError(f"Node {node} missing checksum.")
            if data.get(self.summary_field_id) is None:
                return False
            # Checksum used to be hash_str(document + context) using the above method. This is
            # technically more correct, because the summary context includes adjacent summaries
            # so the whole system updates iteratively. In practice it was just too much looping
            # so for now we just reuse the checksum generated in hierarchy (hash_str(document)).
            summary_checksum = data["checksum"]
            if summary_checksum != data.get(self.checksum_field_id):
                return False
        return True

    async def generate_summary(
        self,
        node: str,
        graph: KnowledgeGraph,
        loading_bar: Optional[tqdm] = None,
        refresh: str | bool = False,
    ):
        """Asynchronously generate summary and update graph"""
        if self.spice_client is None:
            raise RagdaemonError("Spice client not initialized")

        data = graph.nodes[node]
        summary_checksum = data["checksum"]
        _refresh = match_refresh(refresh, node)
        if (
            _refresh
            or data.get(self.summary_field_id) is None
            or summary_checksum != data.get(self.checksum_field_id)
        ):
            document, context = get_document_and_context(
                node,
                graph,
                self.io,
                summary_field_id=self.summary_field_id,
                model=self.model,
            )
            subprompt = "root" if node == "ROOT" else data.get("type", "")
            previous_summary = "" if _refresh else data.get(self.summary_field_id, "")

            messages = SpiceMessages(self.spice_client)
            messages.add_system_prompt(
                name=f"summarizer.{subprompt}", previous_summary=previous_summary
            )
            messages.add_user_prompt(
                name="summarizer.user",
                document=document,
                context=context,
                previous_summary=previous_summary,
            )
            async with semaphore:
                response = await self.spice_client.get_response(
                    messages=messages,
                    model=self.model,
                )
            summary = response.text

            if summary != "PASS":
                data[self.summary_field_id] = summary
            data[self.checksum_field_id] = summary_checksum

        if loading_bar is not None:
            loading_bar.update(1)

    async def dfs(
        self,
        node: str,
        graph: KnowledgeGraph,
        loading_bar: Optional[tqdm] = None,
        refresh: str | bool = False,
    ):
        """Depth-first search to generate summaries for all nodes"""
        children = [
            edge[1]
            for edge in graph.out_edges(node, data=True)
            if edge[-1].get("type") == "hierarchy"
            and graph.nodes[edge[1]].get("type") in self.summarize_nodes
        ]
        if children:
            tasks = [self.dfs(child, graph, loading_bar, refresh) for child in children]
            await asyncio.gather(*tasks)
        await self.generate_summary(node, graph, loading_bar, refresh)

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: str | bool = False
    ) -> KnowledgeGraph:
        """Asynchronously generate or fetch summaries and add to graph/db"""
        summaries = dict[str, str]()
        for node, data in graph.nodes(data=True):
            if data is not None and data.get("type") in self.summarize_nodes:
                summaries[node] = data.get(self.checksum_field_id, "")

        if self.verbose > 1:
            loading_bar = tqdm(total=len(summaries), desc="Summarizing code...")
        else:
            loading_bar = None

        await self.dfs("ROOT", graph, loading_bar, refresh)

        update_db = {"ids": [], "metadatas": []}
        for node, summary_checksum in summaries.items():
            if graph.nodes[node].get(self.checksum_field_id) != summary_checksum:
                data = graph.nodes[node]
                update_db["ids"].append(data["checksum"])
                update_db["metadatas"].append(
                    {
                        self.summary_field_id: data[self.summary_field_id],
                        self.checksum_field_id: data[self.checksum_field_id],
                    }
                )
        if len(update_db["ids"]) > 1:
            update_db = remove_update_db_duplicates(**update_db)
            db.update(**update_db)

        if loading_bar is not None:
            loading_bar.close()

        return graph
