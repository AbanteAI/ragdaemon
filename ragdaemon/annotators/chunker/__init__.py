import asyncio
import json
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import Optional, Set

from astroid.exceptions import AstroidSyntaxError
from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.annotators.chunker.chunk_astroid import chunk_document as chunk_astroid
from ragdaemon.annotators.chunker.chunk_line import chunk_document as chunk_line
from ragdaemon.annotators.chunker.chunk_llm import chunk_document as chunk_llm
from ragdaemon.annotators.chunker.utils import resolve_chunk_parent
from ragdaemon.database import (
    Database,
    remove_add_to_db_duplicates,
    remove_update_db_duplicates,
)
from ragdaemon.errors import RagdaemonError
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import (
    DEFAULT_CODE_EXTENSIONS,
    get_document,
    hash_str,
    match_refresh,
    truncate,
)


class Chunker(Annotator):
    name = "chunker"
    chunk_field_id = "chunks"

    def __init__(
        self, *args, files: Optional[Set[str]] = None, use_llm: bool = False, **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.files = files

        # By default, use either the LLM chunker or a basic line chunker.
        if use_llm and self.spice_client is not None:
            default_chunk_fn = partial(
                chunk_llm, spice_client=self.spice_client, verbose=self.verbose
            )
        else:
            default_chunk_fn = chunk_line

        # For python files, try to use astroid. If that fails, fall back to the default chunker.
        async def python_chunk_fn(document: str):
            try:
                return await chunk_astroid(document)
            except AstroidSyntaxError:
                if self.verbose > 0:
                    file = document.split("\n")[0]
                    print(
                        f"Error chunking {file} with astroid; falling back to default chunker."
                    )
                return await default_chunk_fn(document)

        self.chunk_extensions_map = {}
        for extension in DEFAULT_CODE_EXTENSIONS:
            if extension == ".py":
                self.chunk_extensions_map[extension] = python_chunk_fn
            else:
                self.chunk_extensions_map[extension] = default_chunk_fn

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") != "file":
                continue
            chunks = data.get(self.chunk_field_id, None)
            if chunks is None:
                if self.chunk_extensions_map is None:
                    return False
                extension = Path(data["ref"]).suffix
                if extension in self.chunk_extensions_map:
                    return False
            else:
                if not isinstance(chunks, list):
                    chunks = json.loads(chunks)
                for chunk in chunks:
                    if chunk["id"] not in graph:
                        return False
        return True

    async def get_file_chunk_data(self, node, data):
        """Generate and save chunk data for a file node to graph and db"""
        document = data["document"]
        extension = Path(data["ref"]).suffix
        try:
            chunks = await self.chunk_extensions_map[extension](document)
        except RagdaemonError:
            if self.verbose > 0:
                print(f"Error chunking {node}; skipping.")
            chunks = []
        chunks = sorted(chunks, key=lambda x: len(x["id"]))
        data[self.chunk_field_id] = chunks

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: str | bool = False
    ) -> KnowledgeGraph:
        # Select file nodes and remove all existing chunk nodes from graph.
        files_with_chunks = []
        all_nodes = list(graph.nodes(data=True))
        for node, data in all_nodes:
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") == "chunk":
                graph.remove_node(node)
            elif data.get("type") == "file":
                if self.files is not None and node not in self.files:
                    continue
                if self.chunk_extensions_map is None:
                    files_with_chunks.append((node, data))
                else:
                    extension = Path(data["ref"]).suffix
                    if extension in self.chunk_extensions_map:
                        files_with_chunks.append((node, data))

        # Generate/add chunk data for nodes that don't have it
        tasks = []
        files_just_chunked = set()
        for node, data in files_with_chunks:
            if (
                match_refresh(refresh, node)
                or data.get(self.chunk_field_id, None) is None
            ):
                tasks.append(self.get_file_chunk_data(node, data))
                files_just_chunked.add(node)
            elif isinstance(data[self.chunk_field_id], str):
                data[self.chunk_field_id] = json.loads(data[self.chunk_field_id])
        if len(tasks) > 0:
            if self.verbose > 1:
                await tqdm.gather(*tasks, desc="Chunking files...")
            else:
                await asyncio.gather(*tasks)
            update_db = {"ids": [], "metadatas": []}
            for node in files_just_chunked:
                data = graph.nodes[node]
                update_db["ids"].append(data["checksum"])
                metadatas = {self.chunk_field_id: json.dumps(data[self.chunk_field_id])}
                update_db["metadatas"].append(metadatas)
            update_db = remove_update_db_duplicates(**update_db)
            db.update(**update_db)

        # Process chunks
        # 1. Add all chunks to graph
        checksums = dict[str, str]()
        for file, data in files_with_chunks:
            if len(data[self.chunk_field_id]) == 0:
                continue
            # Sort such that "parents" are added before "children"
            base_id = f"{file}:BASE"
            chunks = [c for c in data[self.chunk_field_id] if c["id"] != base_id]
            chunks.sort(key=lambda x: len(x["id"]))
            base_chunk = [c for c in data[self.chunk_field_id] if c["id"] == base_id]
            if len(base_chunk) != 1:
                raise RagdaemonError(f"Node {file} missing base chunk")
            chunks = base_chunk + chunks
            # Load chunks into graph
            for chunk in chunks:
                id, ref = chunk["id"], chunk["ref"]
                document = get_document(ref, self.io, type="chunk")
                checksum = hash_str(document)
                chunk_data = {
                    "id": id,
                    "ref": ref,
                    "type": "chunk",
                    "document": document,
                    "checksum": checksum,
                }
                graph.add_node(id, **chunk_data)
                checksums[id] = checksum

                all_nodes = set(graph.nodes)
                parent = resolve_chunk_parent(id, all_nodes)
                if parent is None:
                    if self.verbose > 1:
                        print(f"No parent node found for {id}")
                    parent = f"{file}:BASE"
                graph.add_edge(parent, id, type="hierarchy")

        # Sync with remote DB
        ids = list(set(checksums.values()))
        response = db.get(ids=ids, include=["metadatas"])
        db_data = {id: data for id, data in zip(response["ids"], response["metadatas"])}
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for node, checksum in checksums.items():
            if checksum in db_data:
                data = db_data[checksum]
                graph.nodes[node].update(data)
            else:
                data = deepcopy(graph.nodes[node])
                document = data.pop("document")
                document, truncate_ratio = truncate(document, db.embedding_model)
                if truncate_ratio > 0 and self.verbose > 1:
                    print(f"Truncated {node} by {truncate_ratio:.2%}")
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(data)
        if len(add_to_db["ids"]) > 0:
            add_to_db = remove_add_to_db_duplicates(**add_to_db)
            db.add(**add_to_db)

        return graph
