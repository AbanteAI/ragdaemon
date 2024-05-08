import asyncio
import json
from typing import Optional, Any

import numpy as np
from spice import SpiceMessage
from spice.models import TextModel
from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import DEFAULT_COMPLETION_MODEL, hash_str, semaphore

clusterer_binary_prompt = """\
You are building a hierarchical summary of a codebase using agglomerative clustering.
You will be given two one-line summaries of code chunks or existing summaries.
Combine the two summaries into a single one-line summary.

Your summary should concisely answer the question "What does this do?"
Don't aim to give an exhaustive report; instead, focus on what would distinguish this 
particular code from other parts of the codebase.
"""


class ClustererBinary(Annotator):
    name = "cluterer_binary"

    def __init__(
        self,
        *args,
        pipeline: list[Annotator] = [],
        linkage_method: str = "ward",
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        try:
            chunk_field_id = next(
                getattr(a, "chunk_field_id") for a in pipeline if "chunker" in a.name
            )
            summary_field_id = next(
                getattr(a, "summary_field_id")
                for a in pipeline
                if "summarizer" in a.name
            )
        except (StopIteration, AttributeError):
            raise RagdaemonError(
                "ClustererBinary annotator requires a 'chunker' and 'summarizer' annotator with chunk_field_id and summary_field_id."
            )
        self.chunk_field_id = chunk_field_id
        self.summary_field_id = summary_field_id
        self.linkage_method = linkage_method
        self.model = model

    def select_leaf_nodes(self, graph: KnowledgeGraph) -> list[str]:
        leaf_nodes = []
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") != "file":
                continue

            # Determine whether to use the file itself or its chunks
            chunks = data.get(self.chunk_field_id)
            if chunks is None:
                leaf_nodes.append(node)
                continue
            if not isinstance(chunks, list):
                chunks = json.loads(chunks)
            if len(chunks) == 0:
                leaf_nodes.append(node)
            else:
                for chunk in chunks:
                    leaf_nodes.append(chunk["id"])
        return leaf_nodes

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        # Start with a list of all the summary nodes
        cluster_binary_nodes = [
            (node, graph.in_degree(node), graph.out_degree(node))
            for node, data in graph.nodes(data=True)
            if data is not None and data.get("type") == "cluster_binary"
        ]
        root = None
        leaves = set()
        for node, in_degree, out_degree in cluster_binary_nodes:
            if not graph.nodes[node].get("summary"):
                return False  # Each needs a summary
            if out_degree != 2:
                return False  # Each needs 2 successors
            if in_degree == 0:
                if root is not None:
                    return False  # Only one should have no predecessors
                root = node
            else:
                if in_degree != 1:
                    return False  # The rest need 1 predecessor
                for neighbor in graph.successors(node):
                    if graph.nodes[neighbor].get("type") != "cluster_binary":
                        leaves.add(neighbor)
        if root is None:
            return False  # There has to be a root
        expected_leaves = set(self.select_leaf_nodes(graph))
        return leaves == expected_leaves  # All leaves are accounted for

    async def get_llm_response(self, document: str) -> str:
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")
        messages: list[SpiceMessage] = [
            {"role": "system", "content": clusterer_binary_prompt},
            {"role": "user", "content": document},
        ]
        async with semaphore:
            response = await self.spice_client.get_response(
                messages=messages,
                model=self.model,
            )
        return response.text

    async def get_summary(
        self,
        node: str,
        document: str,
        graph: KnowledgeGraph,
        loading_bar: Optional[tqdm] = None,
    ) -> dict[str, Any]:
        """Asynchronously generate summary and update graph and db"""
        summary = await self.get_llm_response(document)
        checksum = hash_str(document)
        record = {
            "id": node,
            "type": "cluster_binary",
            "summary": summary,
            "checksum": checksum,
            "active": False,
        }
        graph.nodes[node].update(record)
        if loading_bar is not None:
            loading_bar.update(1)
        return {"ids": checksum, "documents": document, "metadatas": record}

    async def load_all_summary_nodes(
        self,
        new_nodes: list[str],
        graph: KnowledgeGraph,
        db: Database,
        refresh: bool = False,
    ):
        """Asynchronously generate or fetch summaries and add to graph/db"""
        loading_bar = (
            None
            if not self.verbose
            else tqdm(total=len(new_nodes), desc="Refreshing binary clusters")
        )
        while len(new_nodes) > 0:
            tasks = []
            just_added = set()
            for node in new_nodes:
                a, b = list(graph.successors(node))
                a_summary = graph.nodes[a].get("summary")
                b_summary = graph.nodes[b].get("summary")
                if a_summary is None or b_summary is None:
                    continue
                just_added.add(node)
                document = f"{a_summary}\n{b_summary}"
                checksum = hash_str(document)
                records = db.get(checksum)["metadatas"]
                if refresh or len(records) == 0:
                    tasks.append(self.get_summary(node, document, graph, loading_bar))
                else:
                    record = records[0]
                    graph.nodes[node].update(record)
                    if loading_bar is not None:
                        loading_bar.update(1)

            new_nodes = list(set(new_nodes) - just_added)
            if len(tasks) > 0:
                results = await asyncio.gather(*tasks)
                add_to_db = {"ids": [], "documents": [], "metadatas": []}
                for result in results:
                    for key, value in result.items():
                        add_to_db[key].append(value)
                db.add(**add_to_db)
            elif new_nodes:
                raise RagdaemonError(f"Stuck on nodes {new_nodes}")

        if loading_bar is not None:
            loading_bar.close()

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        try:
            # Scipy is intentionally excluded from package requirements because it's
            # a large package and this is an experimental feature.
            from scipy.cluster.hierarchy import linkage
        except ImportError:
            raise RagdaemonError(
                "ClustererBinary requires scipy to be installed. Run 'pip install scipy'."
            )

        # Remove any existing cluster_binary nodes and edges
        cluster_binary_nodes = [
            node
            for node, data in graph.nodes(data=True)
            if data is not None and data.get("type") == "cluster_binary"
        ]
        graph.remove_nodes_from(cluster_binary_nodes)
        cluster_binary_edges = [
            (e[0], e[1])
            for e in graph.edges(data=True)
            if e[-1].get("type") == "cluster_binary"
        ]
        graph.remove_edges_from(cluster_binary_edges)

        # Generate the linkage_list for active checksums
        leaf_ids = self.select_leaf_nodes(graph)
        leaf_checksums = [graph.nodes[leaf]["checksum"] for leaf in leaf_ids]
        embeddings = db.get(ids=leaf_checksums, include=["embeddings"])["embeddings"]
        data = np.array([np.array(e) for e in embeddings])
        linkage_matrix = linkage(data, method=self.linkage_method)

        # Add empty nodes and edges to the graph
        all_nodes = leaf_ids.copy()
        for i, (a, b, _, height) in enumerate(linkage_matrix):
            i_link = i + len(leaf_ids)
            node = f"summary_{i_link}"
            all_nodes.append(node)
            graph.add_node(node)
            graph.add_edge(node, all_nodes[int(a)], type="cluster_binary")
            graph.add_edge(node, all_nodes[int(b)], type="cluster_binary")

        # Generate/fetch summaries and add to graph/db.
        new_nodes = all_nodes[len(leaf_ids) :]
        try:
            await self.load_all_summary_nodes(new_nodes, graph, db, refresh=refresh)
        except KeyboardInterrupt:
            raise

        return graph
