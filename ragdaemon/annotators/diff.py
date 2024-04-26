import json
import re
from pathlib import Path

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database, remove_add_to_db_duplicates
from ragdaemon.get_paths import get_git_root_for_path
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import get_document, hash_str, parse_path_ref, truncate


def get_chunks_from_diff(id: str, diff: str) -> dict[str, str]:
    # Match files and line numbers
    file_regex = re.compile(r"^diff --git a/(.+) b/(.+)$")
    hunk_header_regex = re.compile(r"^@@ -\d+,\d+ \+(\d+),(\d+) @@.*$")

    chunks = {}
    file = None
    i = None
    chunk_id: str | None = None
    chunk_ref_start = None
    for i, line in enumerate(diff.split("\n")):
        file_match = file_regex.match(line)
        hunk_header_match = hunk_header_regex.match(line)
        if (file_match or hunk_header_match) and (
            file and chunk_id and chunk_ref_start
        ):
            chunk_ref_end = i - 1
            chunk_ref = f"{id}:{chunk_ref_start}-{chunk_ref_end}"
            chunks[chunk_id] = chunk_ref
            chunk_id = None
            chunk_ref_start = None
        if file_match:
            file = file_match.group(2)  # Ending file name
        elif hunk_header_match:
            chunk_ref_start = i
            start_line = int(hunk_header_match.group(1))
            num_lines = int(hunk_header_match.group(2))
            end_line = start_line + num_lines - 1
            if end_line > start_line:
                lines_ref = f":{start_line}-{end_line}"
            elif end_line == start_line:
                lines_ref = f":{start_line}"
            else:
                lines_ref = ""
            chunk_id = f"{id}:{file}{lines_ref}"
    if i and file and chunk_id and chunk_ref_start:
        chunk_ref_end = i
        chunk_ref = f"{id}:{chunk_ref_start}-{chunk_ref_end}"
        chunks[chunk_id] = chunk_ref

    return chunks


def parse_diff_id(id: str) -> tuple[str, Path | None, set[int] | None]:
    if ":" in id:
        diff_ref, path_ref = id.split(":", 1)
        path, lines = parse_path_ref(path_ref)
    else:
        diff_ref, path, lines = id, None, None
    return diff_ref, path, lines


class Diff(Annotator):
    name: str = "diff"

    def __init__(self, *args, diff: str = "", **kwargs):
        if ":" in diff:
            raise RagdaemonError("diff cannot contain ':'")
        super().__init__(*args, **kwargs)
        self.diff_args = diff

    @property
    def id(self) -> str:
        return "DEFAULT" if not self.diff_args else self.diff_args

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        cwd = Path(graph.graph["cwd"])
        if not get_git_root_for_path(cwd, raise_error=False):
            return True

        document = get_document(self.diff_args, cwd, type="diff")
        checksum = hash_str(document)
        return self.id in graph and graph.nodes[self.id]["checksum"] == checksum

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        cwd = Path(graph.graph["cwd"])
        if not get_git_root_for_path(cwd, raise_error=False):
            return graph

        graph_nodes = {
            node
            for node, data in graph.nodes(data=True)
            if data and data.get("type") == "diff"
        }
        graph.remove_nodes_from(graph_nodes)
        document = get_document(self.diff_args, cwd, type="diff")
        checksum = hash_str(document)
        existing_records = db.get(checksum)
        if refresh or len(existing_records["ids"]) == 0:
            chunks = get_chunks_from_diff(id=self.id, diff=document)
            data = {
                "id": self.id,
                "ref": self.diff_args,
                "type": "diff",
                "checksum": checksum,
                "chunks": json.dumps(chunks),
                "active": False,
            }

            # If the full diff is too long to embed, it is truncated. Anything
            # removed will be captured in chunks.
            document, truncate_ratio = truncate(document, db.embedding_model)
            if truncate_ratio > 0 and self.verbose:
                print(f"Truncated diff by {truncate_ratio:.2%}")
            db.upsert(ids=checksum, documents=document, metadatas=data)
        else:
            data = existing_records["metadatas"][0]
        data["chunks"] = json.loads(data["chunks"])
        graph.add_node(self.id, **data)

        # Add chunks
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        edges_to_add = set()
        for chunk_id, chunk_ref in data["chunks"].items():
            document = get_document(chunk_ref, cwd, type="diff")
            chunk_checksum = hash_str(document)
            existing_records = db.get(chunk_checksum)
            if refresh or len(existing_records["ids"]) == 0:
                data = {
                    "id": chunk_id,
                    "ref": chunk_ref,
                    "type": "diff",
                    "checksum": chunk_checksum,
                    "active": False,
                }
                document, truncate_ratio = truncate(document, db.embedding_model)
                if truncate_ratio < 1 and self.verbose:
                    print(f"Truncated diff chunk {chunk_id} by {truncate_ratio:.2%}")
                add_to_db["ids"].append(chunk_checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(data)
            else:
                data = existing_records["metadatas"][0]
            graph.add_node(chunk_id, **data)
            edges_to_add.add((self.id, chunk_id))
            # Match file/chunk nodes in graph
            path_ref = chunk_id.split(":", 1)[1]
            file, lines = parse_path_ref(path_ref)
            file_str = str(file)
            if file_str not in graph:  # Removed files
                if self.verbose:
                    print(f"File {file_str} not in graph")
                continue
            edges_to_add.add((chunk_id, file_str))

            def _link_to_successors(_node, visited=set()):
                for successor in graph.successors(_node):
                    if successor in visited:
                        continue
                    visited.add(successor)
                    edge = (chunk_id, successor)
                    _data = graph.nodes[successor]
                    if _data.get("type") not in ["file", "chunk"]:
                        continue
                    _, _lines = parse_path_ref(_data["ref"])
                    if lines and _lines and lines.intersection(_lines):
                        edges_to_add.add(edge)
                    _link_to_successors(successor, visited)

            _link_to_successors(file_str)

        for source, origin in edges_to_add:
            graph.add_edge(source, origin, type="diff")
        if len(add_to_db["ids"]) > 0:
            add_to_db = remove_add_to_db_duplicates(**add_to_db)
            db.upsert(**add_to_db)

        return graph
