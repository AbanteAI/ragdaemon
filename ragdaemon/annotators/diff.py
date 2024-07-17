import json
import re
from copy import deepcopy

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database, remove_add_to_db_duplicates
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import (
    get_document,
    hash_str,
    parse_diff_id,
    parse_path_ref,
    truncate,
)


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
        if not self.io.is_git_repo():
            return True

        document = get_document(self.diff_args, self.io, type="diff")
        checksum = hash_str(document)
        return self.id in graph and graph.nodes[self.id]["checksum"] == checksum

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: str | bool = False
    ) -> KnowledgeGraph:
        if not self.io.is_git_repo():
            return graph

        graph_nodes = {
            node
            for node, data in graph.nodes(data=True)
            if data and data.get("type") == "diff"
        }
        graph.remove_nodes_from(graph_nodes)

        checksums = dict[str, str]()
        document = get_document(self.diff_args, self.io, type="diff")
        checksum = hash_str(document)
        chunks = get_chunks_from_diff(id=self.id, diff=document)
        data = {
            "id": self.id,
            "ref": self.diff_args,
            "type": "diff",
            "document": document,
            "checksum": checksum,
            "chunks": chunks,
        }
        graph.add_node(self.id, **data)
        checksums[self.id] = checksum

        for chunk_id, chunk_ref in chunks.items():
            document = get_document(chunk_ref, self.io, type="diff")
            chunk_checksum = hash_str(document)
            data = {
                "id": chunk_id,
                "ref": chunk_ref,
                "type": "diff",
                "document": document,
                "checksum": chunk_checksum,
            }
            graph.add_node(chunk_id, **data)
            graph.add_edge(self.id, chunk_id, type="diff")
            checksums[chunk_id] = chunk_checksum

            # Link it to all overlapping chunks (if file has chunks) or to the file
            _, path, lines = parse_diff_id(chunk_id)
            if not path:
                continue
            path_str = path.as_posix()
            if path_str not in graph:  # Removed files
                if self.verbose > 1:
                    print(f"File {path_str} not in graph")
                continue
            link_to = set()
            for node, data in graph.nodes(data=True):
                if not node.startswith(f"{path_str}:") or data.get("type") != "chunk":
                    continue
                _, _lines = parse_path_ref(data["ref"])
                if lines and _lines and lines.intersection(_lines):
                    link_to.add(node)
            if len(link_to) == 0:
                link_to.add(path_str)
            for node in link_to:
                graph.add_edge(node, chunk_id, type="link")

        # Sync with remote DB
        ids = list(set(checksums.values()))
        response = db.get(ids=ids, include=[])
        db_data = set(response["ids"])
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for id, checksum in checksums.items():
            if checksum in db_data:
                continue
            data = deepcopy(graph.nodes[id])
            document = data.pop("document")
            if "chunks" in data:
                data["chunks"] = json.dumps(data["chunks"])
            document, truncate_ratio = truncate(document, db.embedding_model)
            if self.verbose > 1 and truncate_ratio > 0:
                print(f"Truncated {id} by {truncate_ratio:.2%}")
            add_to_db["ids"].append(checksum)
            add_to_db["documents"].append(document)
            add_to_db["metadatas"].append(data)
        if len(add_to_db["ids"]) > 0:
            add_to_db = remove_add_to_db_duplicates(**add_to_db)
            db.add(**add_to_db)

        return graph
