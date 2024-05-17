"""
Chunk data a list of objects following [
    {id: path/to/file:class.method, start_line: int, end_line: int}
]

It's stored on the file node as data['chunks'] and json.dumped into the database.

A chunker annotator:
1. Is complete when all files (with matching extensions) have a 'chunks' field
2. Generates chunks using a subclass method (llm, ctags..)
3. Adds that data to each file's graph node and database record
4. Add graph nodes (and db records) for each of those chunks
5. Add hierarchy edges connecting everything back to cwd

The Chunker base class below handles everything except step 2.
"""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import (
    Database,
    remove_add_to_db_duplicates,
    remove_update_db_duplicates,
)
from ragdaemon.errors import RagdaemonError
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import DEFAULT_CODE_EXTENSIONS, get_document, hash_str, truncate


class Chunker(Annotator):
    name = "chunker"
    chunk_field_id = "chunks"

    def __init__(self, *args, chunk_extensions: Optional[list[str]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        if chunk_extensions is None:
            chunk_extensions = DEFAULT_CODE_EXTENSIONS
        self.chunk_extensions = chunk_extensions

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") != "file":
                continue
            chunks = data.get(self.chunk_field_id, None)
            if chunks is None:
                if self.chunk_extensions is None:
                    return False
                extension = Path(data["ref"]).suffix
                if extension in self.chunk_extensions:
                    return False
            else:
                if not isinstance(chunks, list):
                    chunks = json.loads(chunks)
                for chunk in chunks:
                    if chunk["id"] not in graph:
                        return False
        return True

    async def chunk_document(self, document: str) -> list[dict[str, Any]]:
        """Return a list of {id, ref} chunks for the given document."""
        raise NotImplementedError()

    async def get_file_chunk_data(self, node, data):
        """Generate and save chunk data for a file node to graph and db"""
        document = data["document"]
        try:
            chunks = await self.chunk_document(document)
        except RagdaemonError:
            if self.verbose:
                print(f"Error chunking {node}; skipping.")
            chunks = []
        chunks = sorted(chunks, key=lambda x: len(x["id"]))
        data[self.chunk_field_id] = chunks

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
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
                if self.chunk_extensions is None:
                    files_with_chunks.append((node, data))
                else:
                    extension = Path(data["ref"]).suffix
                    if extension in self.chunk_extensions:
                        files_with_chunks.append((node, data))

        # Generate/add chunk data for nodes that don't have it
        tasks = []
        files_just_chunked = set()
        for node, data in files_with_chunks:
            if refresh or data.get(self.chunk_field_id, None) is None:
                tasks.append(self.get_file_chunk_data(node, data))
                files_just_chunked.add(node)
            elif isinstance(data[self.chunk_field_id], str):
                data[self.chunk_field_id] = json.loads(data[self.chunk_field_id])
        if len(tasks) > 0:
            if self.verbose:
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
        all_chunk_ids = set()
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
                document = get_document(ref, Path(graph.graph["cwd"]))
                chunk_data = {
                    "id": id,
                    "ref": ref,
                    "type": "chunk",
                    "document": document,
                    "checksum": hash_str(document),
                    "active": False,
                }
                graph.add_node(id, **chunk_data)
                all_chunk_ids.add(id)
                # Locate the parent and add hierarchy edge
                chunk_str = id.split(":")[1]
                if chunk_str == "BASE":
                    parent = file
                elif "." not in chunk_str:
                    parent = base_id
                else:
                    parts = chunk_str.split(".")
                    while True:
                        parent = f"{file}:{'.'.join(parts[:-1])}"
                        if parent in graph:
                            break
                        parent_str = parent.split(":")[1]
                        if "." not in parent_str:
                            # If we can't find a parent, use the base node.
                            if self.verbose:
                                print(f"No parent node found for {id}")
                            parent = base_id
                            break
                        # If intermediate parents are missing, skip them
                        parts = parent_str.split(".")
                graph.add_edge(parent, id, type="hierarchy")

        # 2. Get metadata for all chunks from db
        all_chunk_checksums = [
            graph.nodes[chunk]["checksum"] for chunk in all_chunk_ids
        ]
        response = db.get(ids=all_chunk_checksums, include=["metadatas"])
        db_data = {data["id"]: data for data in response["metadatas"]}
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for chunk in all_chunk_ids:
            if chunk in db_data:
                # 3. Add db metadata for nodes that have it
                graph.nodes[chunk].update(db_data[chunk])
            else:
                # 4. Add to db nodes that don't
                data = deepcopy(graph.nodes[chunk])
                document = data.pop("document")
                document, truncate_ratio = truncate(document, db.embedding_model)
                if truncate_ratio > 0 and self.verbose:
                    print(f"Truncated {chunk} by {truncate_ratio:.2%}")
                add_to_db["ids"].append(data["checksum"])
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(data)
        if len(add_to_db["ids"]) > 0:
            add_to_db = remove_add_to_db_duplicates(**add_to_db)
            db.add(**add_to_db)

        return graph
