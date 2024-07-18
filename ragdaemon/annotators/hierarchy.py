from copy import deepcopy
from pathlib import Path

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database, remove_add_to_db_duplicates
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.io import IO
from ragdaemon.utils import get_document, hash_str, truncate


def files_checksum(io: IO, ignore_patterns: set[Path] = set()) -> str:
    timestamps = ""
    for path in io.get_paths_for_directory(exclude_patterns=ignore_patterns):
        try:
            timestamps += str(io.last_modified(path))
        except FileNotFoundError:
            pass
    return hash_str(timestamps)


class Hierarchy(Annotator):
    name = "hierarchy"

    def __init__(self, *args, ignore_patterns: set[Path] = set(), **kwargs):
        # match_path_with_patterns expects type abs_path, even if it's a glob
        self.ignore_patterns = {Path(p).resolve() for p in ignore_patterns}
        super().__init__(*args, **kwargs)

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        return graph.graph.get("files_checksum") == files_checksum(
            self.io, self.ignore_patterns
        )

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: str | bool = False
    ) -> KnowledgeGraph:
        """Build a graph of active files and directories with hierarchy edges."""

        # Initialize a new graph from scratch with same cwd
        cwd = Path(graph.graph["cwd"])
        graph = KnowledgeGraph()
        graph.graph["cwd"] = str(cwd)

        # Load active files/dirs and checksums
        checksums = dict[Path, str]()
        paths = self.io.get_paths_for_directory(exclude_patterns=self.ignore_patterns)
        directories = set()
        edges = set()
        for path in paths:
            path_str = path.as_posix()
            document = get_document(path_str, self.io)
            checksum = hash_str(document)
            data = {
                "id": path_str,
                "type": "file",
                "ref": path_str,
                "document": document,
                "checksum": checksum,
            }
            graph.add_node(path_str, **data)
            checksums[path] = checksum
            # Record parents & edges
            _last = path
            for parent in path.parents:
                if len(parent.parts) == 0:
                    parent = Path("ROOT")
                directories.add(parent.as_posix())
                edges.add((parent.as_posix(), _last.as_posix()))
                _last = parent

        for source, target in edges:
            for id in (source, target):
                if id not in graph and id not in directories:
                    raise RagdaemonError(f"Node {id} not found in graph")
            graph.add_edge(source, target, type="hierarchy")

        # Fill-in directory data (same process as get_document for dirs, but more efficient)
        for dir in sorted(
            directories, key=lambda x: len(x) if x != "ROOT" else 0, reverse=True
        ):
            children = sorted(node for node in graph.successors(dir))
            document = f"{dir}\n" + "\n".join(children)
            checksum = hash_str("".join(checksums[Path(child)] for child in children))
            data = {
                "id": dir,
                "type": "directory",
                "ref": dir,
                "document": document,
                "checksum": checksum,
            }
            checksums[Path(dir)] = checksum
            graph.nodes[dir].update(data)

        # Sync with remote DB
        ids = list(set(checksums.values()))
        response = db.get(ids=ids, include=["metadatas"])
        db_data = {id: data for id, data in zip(response["ids"], response["metadatas"])}
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for path, checksum in checksums.items():
            if checksum in db_data:
                data = db_data[checksum]
                graph.nodes[path.as_posix()].update(data)
            else:
                data = deepcopy(graph.nodes[path.as_posix()])
                document = data.pop("document")
                document, truncate_ratio = truncate(document, db.embedding_model)
                if self.verbose > 1 and truncate_ratio > 0:
                    print(f"Truncated {path} by {truncate_ratio:.2%}")
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(data)
        if len(add_to_db["ids"]) > 0:
            add_to_db = remove_add_to_db_duplicates(**add_to_db)
            db.add(**add_to_db)

        graph.graph["files_checksum"] = files_checksum(self.io, self.ignore_patterns)
        return graph
