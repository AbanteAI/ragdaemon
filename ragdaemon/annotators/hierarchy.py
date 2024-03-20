import fnmatch
from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import MAX_TOKENS_PER_EMBEDDING, get_db
from ragdaemon.errors import RagdaemonError
from ragdaemon.llm import token_counter
from ragdaemon.utils import get_document, get_non_gitignored_files, hash_str


def match_path_with_patterns(path: Path, cwd: Path, patterns: list[str] = []) -> bool:
    """Check if the given absolute path matches any of the patterns.

    Args:
        `path` - An absolute path
        `patterns` - A set of absolute paths/glob patterns

    Return:
        A boolean flag indicating if the path matches any of the patterns
    """
    if not path.is_absolute():
        path = cwd / path
    for pattern in patterns:
        # Check if the pattern is a glob pattern match
        if fnmatch.fnmatch(str(path), str(pattern)):
            return True
        pattern = Path(pattern)
        if not pattern.is_absolute():
            pattern = cwd / pattern
        # Check if the path is relative to the pattern
        if path.is_relative_to(pattern):
            return True
    return False


def get_active_checksums(
    cwd: Path,
    refresh: bool = False,
    verbose: bool = False,
    ignore_patterns: list[str] = [],
) -> dict[Path:str]:
    checksums: dict[Path:str] = {}
    git_paths = get_non_gitignored_files(cwd)
    add_to_db = {
        "ids": [],
        "documents": [],
        "metadatas": [],
    }
    for path in git_paths:
        if match_path_with_patterns(path, cwd, ignore_patterns):
            continue
        try:
            path_str = path.as_posix()
            ref = path_str
            document = get_document(ref, cwd)
            tokens = token_counter(document)
            if tokens > MAX_TOKENS_PER_EMBEDDING:  # e.g. package-lock.json
                continue
            checksum = hash_str(document)
            existing_record = len(get_db(cwd).get(checksum)["ids"]) > 0
            if refresh or not existing_record:
                # add new items to db (will generate embeddings)
                metadatas = {
                    "id": path_str,
                    "type": "file",
                    "ref": ref,
                    "checksum": checksum,
                    "active": False,
                }
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(metadatas)
            checksums[path] = checksum
        except UnicodeDecodeError:  # Ignore non-text files
            pass
        except RagdaemonError as e:
            if verbose:
                print(f"Error processing path {path}: {e}")
    if len(add_to_db["ids"]) > 0:
        get_db(cwd).upsert(**add_to_db)
    return checksums


class Hierarchy(Annotator):
    name = "hierarchy"

    def __init__(self, *args, ignore_patterns: list[str] = [], **kwargs):
        self.ignore_patterns = ignore_patterns
        super().__init__(*args, **kwargs)

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        cwd = Path(graph.graph["cwd"])
        checksums = get_active_checksums(
            cwd, verbose=self.verbose, ignore_patterns=self.ignore_patterns
        )
        files_checksum = hash_str("".join(sorted(checksums.values())))
        return graph.graph.get("files_checksum") == files_checksum

    async def annotate(
        self, old_graph: nx.MultiDiGraph, refresh: bool = False
    ) -> nx.MultiDiGraph:
        """Build a graph of active files and directories with hierarchy edges."""
        cwd = Path(old_graph.graph["cwd"])
        checksums = get_active_checksums(
            cwd,
            refresh=refresh,
            verbose=self.verbose,
            ignore_patterns=self.ignore_patterns,
        )
        files_checksum = hash_str("".join(sorted(checksums.values())))

        # Initialize an empty graph. We'll build it from scratch.
        graph = nx.MultiDiGraph()
        graph.graph["cwd"] = str(cwd)
        edges_to_add = set()
        for path, checksum in checksums.items():
            # add db reecord
            id = path.as_posix()
            results = get_db(cwd).get(checksum)
            data = results["metadatas"][0]
            graph.add_node(id, **data)

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
                    # add directories to graph (to link hierarchy) but not db
                    record = {"id": id, "type": "directory", "ref": id}
                    graph.add_node(id, **record)
            graph.add_edge(source, target, type="hierarchy")

        graph.graph["files_checksum"] = files_checksum
        return graph
