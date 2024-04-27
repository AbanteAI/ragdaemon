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
from typing import Any, Optional

from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database, remove_add_to_db_duplicates
from ragdaemon.errors import RagdaemonError
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import get_document, hash_str, truncate


def is_chunk_valid(chunk: dict) -> bool:
    # Includes the correct fields
    if not set(chunk.keys()) == {"id", "start_line", "end_line"}:
        return False
    # ID is in the correct format
    if not chunk["id"].count(":") == 1:
        return False
    # A chunk name is specified
    if not len(chunk["id"].split(":")[1]):
        return False
    # TODO: Validate the ref, i.e. a parent chunk exists

    return True


def add_file_chunks_to_graph(
    file: str,
    data: dict,
    chunk_field_id: str,
    graph: KnowledgeGraph,
    db: Database,
    refresh: bool = False,
    verbose: bool = False,
) -> dict[str, list[Any]]:
    """Load chunks from file data into db/graph"""
    add_to_db = {"ids": [], "documents": [], "metadatas": []}
    if not isinstance(data[chunk_field_id], list):
        data[chunk_field_id] = json.loads(data[chunk_field_id])
    chunks = data[chunk_field_id]
    if not refresh and len(data[chunk_field_id]) == 0:
        return add_to_db
    edges_to_add = set()
    base_id = f"{file}:BASE"
    edges_to_add.add((file, base_id))
    for chunk in chunks:
        try:
            # Get the checksum record from database
            id = chunk["id"]
            ref = chunk["ref"]
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
                if truncate_ratio > 0 and verbose:
                    print(f"Truncated {id} by {truncate_ratio:.2%}")
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(record)
        except Exception as e:
            if verbose:
                print(f"Error processing chunk {chunk}: {e}")
            continue

        # Load into graph with edges
        graph.add_node(record["id"], **record)

        def _link_to_base_chunk(_id):
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

        _link_to_base_chunk(id)
    for source, origin in edges_to_add:
        graph.add_edge(source, origin, type="hierarchy")
    return add_to_db


class Chunker(Annotator):
    name = "chunker"
    chunk_field_id = "chunks"

    def __init__(self, *args, chunk_extensions: Optional[list[str]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        if chunk_extensions is None:
            chunk_extensions = [
                ".py",
                ".js",
                ".java",
                ".html",
                ".css",
                ".sql",
                ".php",
                ".rb",
                ".sh",
                ".c",
                ".cpp",
                ".h",
                ".hpp",
                ".cs",
                ".go",
                ".ts",
                ".jsx",
                ".tsx",
                ".scss",
            ]
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

    async def chunk_file(
        self, cwd: Path, node: str, data: dict[str, Any], db: Database
    ):
        """Add chunks records {id, ref} to file nodes in graph and db."""
        raise NotImplementedError()

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        files_with_chunks = []  # List of (node, data) tuples
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") == "chunk":
                graph.remove_node(node)  # Remove existing chunk nodes to re-add later
            elif data.get("type") == "file":
                if self.chunk_extensions is None:
                    files_with_chunks.append(node)
                else:
                    extension = Path(data["ref"]).suffix
                    if extension in self.chunk_extensions:
                        files_with_chunks.append((node, data))

        # Generate/add chunk data to file nodes
        tasks = []
        cwd = Path(graph.graph["cwd"])
        for node, data in files_with_chunks:
            if refresh or data.get(self.chunk_field_id, None) is None:
                tasks.append(
                    self.chunk_file(
                        cwd,
                        node,
                        data,
                        db,
                    )
                )
        if len(tasks) > 0:
            if self.verbose:
                await tqdm.gather(*tasks, desc="Chunking files...")
            else:
                await asyncio.gather(*tasks)

        # Load chunk nodes and edges into database and graph
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for file, data in files_with_chunks:
            _add_to_db = add_file_chunks_to_graph(
                file, data, self.chunk_field_id, graph, db, verbose=self.verbose
            )
            for field, values in _add_to_db.items():
                add_to_db[field].extend(values)
        if len(add_to_db["ids"]) > 0:
            add_to_db = remove_add_to_db_duplicates(**add_to_db)
            db.upsert(**add_to_db)
        return graph
