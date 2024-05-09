from pathlib import Path

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database, remove_add_to_db_duplicates
from ragdaemon.get_paths import get_paths_for_directory
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import get_document, hash_str, truncate


def get_active_checksums(
    cwd: Path,
    db: Database,
    refresh: bool = False,
    verbose: bool = False,
    ignore_patterns: set[Path] = set(),
) -> dict[Path, str]:
    # Get checksums for all active files
    checksums: dict[Path, str] = {}
    paths = get_paths_for_directory(cwd, exclude_patterns=ignore_patterns)
    add_to_db = {
        "ids": [],
        "documents": [],
        "metadatas": [],
    }
    for path in paths:
        try:
            path_str = path.as_posix()
            ref = path_str
            document = get_document(ref, cwd)
            checksum = hash_str(document)
            existing_record = len(db.get(checksum)["ids"]) > 0
            if refresh or not existing_record:
                # add new items to db (will generate embeddings)
                metadatas = {
                    "id": path_str,
                    "type": "file",
                    "ref": ref,
                    "checksum": checksum,
                    "active": False,
                }
                document, truncate_ratio = truncate(document, db.embedding_model)
                if truncate_ratio > 0 and verbose:
                    print(f"Truncated {path_str} by {truncate_ratio:.2%}")
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(metadatas)
            checksums[path] = checksum
        except UnicodeDecodeError:  # Ignore non-text files
            pass
        except RagdaemonError as e:
            if verbose:
                print(f"Error processing path {path}: {e}")

    # Get checksums for all active directories
    directories = set()
    for path in paths:
        for parent in path.parents:
            if parent not in paths:
                directories.add(parent)
    for path in directories:
        ref = path.as_posix()
        document = get_document(ref, cwd, type="directory")

        # The checksum for a directory is the hash of the checksums of its subpaths,
        # which are listed in the document and were computed above.
        subdir_checksums = ""
        for subpath in document.split("\n")[1:]:
            subpath = Path(ref) / subpath
            if subpath in checksums:
                subdir_checksums += checksums[subpath]
            else:
                raise RagdaemonError(f"Checksum not found for {subpath}")
        checksum = hash_str(subdir_checksums)

        existing_record = len(db.get(checksum)["ids"]) > 0
        if refresh or not existing_record:
            metadatas = {
                "id": ref,
                "type": "directory",
                "ref": ref,
                "checksum": checksum,
                "active": False,
            }
            document, truncate_ratio = truncate(document, db.embedding_model)
            if truncate_ratio > 0 and verbose:
                print(f"Truncated {ref} by {truncate_ratio:.2%}")
            add_to_db["ids"].append(checksum)
            add_to_db["documents"].append(document)
            add_to_db["metadatas"].append(metadatas)
        checksums[path] = checksum

    if len(add_to_db["ids"]) > 0:
        add_to_db = remove_add_to_db_duplicates(**add_to_db)
        db.upsert(**add_to_db)
    return checksums


def files_checksum(cwd: Path, ignore_patterns: set[Path] = set()) -> str:
    timestamps = ""
    for path in get_paths_for_directory(cwd, exclude_patterns=ignore_patterns):
        try:
            timestamps += str(path.stat().st_mtime)
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
        cwd = Path(graph.graph["cwd"])
        return graph.graph.get("files_checksum") == files_checksum(
            cwd, self.ignore_patterns
        )

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        """Build a graph of active files and directories with hierarchy edges."""
        cwd = Path(graph.graph["cwd"])
        checksums = get_active_checksums(
            cwd,
            db,
            refresh=refresh,
            verbose=self.verbose,
            ignore_patterns=self.ignore_patterns,
        )
        _files_checksum = files_checksum(cwd, self.ignore_patterns)

        # Initialize an empty graph. We'll build it from scratch.
        graph = KnowledgeGraph()
        graph.graph["cwd"] = str(cwd)
        edges_to_add = set()
        for path, checksum in checksums.items():
            # add db reecord
            id = path.as_posix() if len(path.parts) > 0 else "ROOT"
            results = db.get(checksum)
            data = results["metadatas"][0]
            graph.add_node(id, **data)
            if id == "ROOT":
                continue

            # add hierarchy edges
            def _link_to_cwd(_path: Path):
                _parent = _path.parent.as_posix() if len(_path.parts) > 1 else "ROOT"
                edges_to_add.add((_parent, _path.as_posix()))
                if _parent != "ROOT":
                    _link_to_cwd(_path.parent)

            _link_to_cwd(path)

        # Add directory nodes with checksums
        for source, target in edges_to_add:
            for id in (source, target):
                if id not in graph:
                    raise RagdaemonError(f"Node {id} not found in graph")
            graph.add_edge(source, target, type="hierarchy")

        graph.graph["files_checksum"] = _files_checksum
        return graph
