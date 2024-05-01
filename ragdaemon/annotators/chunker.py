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
from pathlib import Path
from typing import Any, Coroutine, Optional

from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database, remove_add_to_db_duplicates
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

    async def get_file_chunk_data(self, node, data, db):
        """Generate and save chunk data for a file node to graph and db"""
        record = db.get(data["checksum"])
        document = record["documents"][0]
        try:
            chunks = await self.chunk_document(document)
        except RagdaemonError:
            if self.verbose:
                print(f"Error chunking {node}; skipping.")
            chunks = []
        # Save to db and graph
        metadatas = record["metadatas"][0]
        metadatas[self.chunk_field_id] = json.dumps(chunks)
        db.update(data["checksum"], metadatas=metadatas)
        data[self.chunk_field_id] = chunks

    def add_file_chunks_to_graph(
        self,
        file: str,
        data: dict,
        graph: KnowledgeGraph,
        db: Database,
        refresh: bool = False,
    ) -> dict[str, list[Any]]:
        """Load chunks from file data into db/graph"""

        # Grab and validate chunks for given file
        chunks = data.get(self.chunk_field_id)
        if chunks is None:
            raise RagdaemonError(f"Node {file} missing {self.chunk_field_id}")
        if isinstance(chunks, str):
            chunks = json.loads(chunks)
            data[self.chunk_field_id] = chunks
        base_id = f"{file}:BASE"
        if len(chunks) > 0 and not any(chunk["id"] == base_id for chunk in chunks):
            raise RagdaemonError(f"Node {file} missing base chunk")
        edges_to_add = {(file, base_id)}
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for chunk in chunks:
            # Locate or create record for chunk
            id, ref = chunk["id"], chunk["ref"]
            document = get_document(ref, Path(graph.graph["cwd"]))
            checksum = hash_str(document)
            records = db.get(checksum)["metadatas"]
            if not refresh and len(records) > 0:
                record = records[0]
            else:
                record = {
                    "id": id,
                    "type": "chunk",
                    "ref": chunk["ref"],
                    "checksum": checksum,
                    "active": False,
                }
                document, truncate_ratio = truncate(document, db.embedding_model)
                if truncate_ratio > 0 and self.verbose:
                    print(f"Truncated {id} by {truncate_ratio:.2%}")
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(record)

            # Add chunk to graph and connect hierarchy edges
            graph.add_node(record["id"], **record)

            def _link_to_base_chunk(_id):
                """Recursively create links from _id to base chunk."""
                path_str, chunk_str = _id.split(":")
                chunk_list = chunk_str.split(".")
                _parent = (
                    f"{path_str}:{'.'.join(chunk_list[:-1])}"
                    if len(chunk_list) > 1
                    else base_id
                )
                edges_to_add.add((_parent, _id))
                if _parent != base_id:
                    _link_to_base_chunk(_parent)

            if id != base_id:
                _link_to_base_chunk(id)
        for source, target in edges_to_add:
            graph.add_edge(source, target, type="hierarchy")
        return add_to_db

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
                tasks.append(self.get_file_chunk_data(node, data, db))
                files_just_chunked.add(node)
        if len(tasks) > 0:
            if self.verbose:
                await tqdm.gather(*tasks, desc="Chunking files...")
            else:
                await asyncio.gather(*tasks)

        # Process chunks
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        remove_from_db = set()
        for file, data in files_with_chunks:
            try:
                refresh = refresh or file in files_just_chunked
                _add_to_db = self.add_file_chunks_to_graph(
                    file, data, graph, db, refresh
                )
                for field, values in _add_to_db.items():
                    add_to_db[field].extend(values)
            except RagdaemonError as e:
                # If there's a problem with the chunks, remove the file from the db.
                # This, along with 'files_just_chunked', prevents invalid database
                # records perpetuating.
                if self.verbose:
                    print(f"Error adding chunks for {file}:\n{e}. Removing db record.")
                remove_from_db.add(data["checksum"])
                continue
        if len(remove_from_db) > 0:
            db.delete(list(remove_from_db))
            raise RagdaemonError(f"Chunking error, try again.")
        if len(add_to_db["ids"]) > 0:
            add_to_db = remove_add_to_db_duplicates(**add_to_db)
            db.upsert(**add_to_db)
        return graph
