import asyncio
import json
from collections import defaultdict
from typing import Optional

import numpy as np
from spice import SpiceMessage
from spice.models import TextModel
from scipy.cluster.hierarchy import linkage
from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import DEFAULT_COMPLETION_MODEL, hash_str, semaphore

summarizer_agglomerative_prompt = """\
You are building a hierarchical summary of a codebase using agglomerative clustering.
You will be given two one-line summaries of code chunks or existing summaries.
Combine the two summaries into a single one-line summary.

Your summary should concisely answer the question "What does this do?"
Don't aim to give an exhaustive report; instead, focus on what would distinguish this 
particular code from other parts of the codebase.
"""

# TODO: Add a node_type to the search function so these summary nodes don't gunk up
# the works.

class SummarizerAgglomerative(Annotator):
    name = "agglomerative_summarizer"

    def __init__(
        self,
        *args,
        chunk_field_id: Optional[str] = None,
        summary_field_id: Optional[str] = None,
        linkage_method: str = "ward",
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
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
        agglomerative_summary_nodes = [
            (node, graph.in_degree(node), graph.out_degree(node))
            for node, data in graph.nodes(data=True)
            if data is not None and data.get("type") == "agglomerative_summary"
        ]
        root = None
        leaves = set()
        for node, in_degree, out_degree in agglomerative_summary_nodes:
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
                    if graph.nodes[neighbor].get("type") != "agglomerative_summary":
                        leaves.add(neighbor)
        if root is None:
            return False  # There has to be a root
        expected_leaves = set(self.select_leaf_nodes(graph))
        return leaves == expected_leaves  # All leaves are accounted for

    async def get_llm_response(self, document: str) -> str:
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")
        messages: list[SpiceMessage] = [
            {"role": "system", "content": summarizer_agglomerative_prompt},
            {"role": "user", "content": document},
        ]
        async with semaphore:
            response = await self.spice_client.get_response(
                messages=messages,
                model=self.model,
            )
        return response.text

    async def get_summary(self, node: str, document: str, graph: KnowledgeGraph, db: Database):
        """Asynchronously generate summary and update graph and db"""
        summary = await self.get_llm_response(document)
        checksum = hash_str(document)
        record = {
            "id": node,
            "type": "agglomerative_summary",
            "summary": summary,
            "checksum": checksum,
            "active": False,
        }
        db.upsert(ids=checksum, documents=document, metadatas=record)
        graph.nodes[node].update(record)

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        # Remove any existing agglomerative_summary nodes and edges
        agglomerative_nodes = [
            node
            for node, data in graph.nodes(data=True)
            if data is not None and data.get("type") == "agglomerative_summary"
        ]
        graph.remove_nodes_from(agglomerative_nodes)
        agglomerative_edges = [
            (e[0], e[1])
            for e in graph.edges(data=True)
            if e[-1].get("type") == "agglomerative_summary"
        ]
        graph.remove_edges_from(agglomerative_edges)
        
        # Generate the linkage_list for active checksums
        leaf_ids = self.select_leaf_nodes(graph)
        leaf_checksums = [graph.nodes[leaf]["checksum"] for leaf in leaf_ids]
        embeddings = db.get(ids=leaf_checksums, include=["embeddings"])["embeddings"]
        data = np.array([np.array(e) for e in embeddings])
        linkage_matrix = linkage(data, method=self.linkage_method)
        
        # Add empty nodes and edges, organize by height
        index = {i: leaf for i, leaf in enumerate(leaf_ids)}
        summary_nodes_by_height = defaultdict(list)
        for i, (a, b, _, height) in enumerate(linkage_matrix):
            i_link = i + len(leaf_ids)
            node = f"summary_{i_link}"
            index[i_link] = node
            graph.add_node(node)
            graph.add_edge(node, index[int(a)], type="agglomerative_summary")
            graph.add_edge(node, index[int(b)], type="agglomerative_summary")
            summary_nodes_by_height[int(height)].append(node)

        # Generate/fetch summaries and add to graph/db
        for height, links in summary_nodes_by_height.items():
            tasks = []
            for node in links:
                successors = list(graph.successors(node))
                if len(successors) != 2:
                    raise RagdaemonError(f"Node {node} has {len(successors)} successors.")
                a, b = successors
                a_summary = graph.nodes[a].get("summary")
                b_summary = graph.nodes[b].get("summary")
                if a_summary is None or b_summary is None:
                    raise RagdaemonError("Both nodes must have summaries.")
                document = f"{a_summary}\n{b_summary}"
                checksum = hash_str(document)
                records = db.get(checksum)["metadatas"]
                if refresh or len(records) == 0:
                    tasks.append(self.get_summary(node, document, graph, db))
                else:
                    record = records[0]
                    graph.nodes[node].update(record)

            if len(tasks) > 0:
                if self.verbose:
                    await tqdm.gather(*tasks, desc=f"Generating agglomerative summaries level {height}")
                else:
                    await asyncio.gather(*tasks)

        return graph
