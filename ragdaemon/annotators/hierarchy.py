import os
import subprocess
from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import get_db
from ragdaemon.utils import hash_str, get_document


def get_active_checksums(cwd: Path, refresh: bool = False) -> dict[Path: str]:
    checksums: dict[Path: str] = {}
    git_paths = set(  # All non-ignored and untracked files
        Path(os.path.normpath(p))
        for p in filter(
            lambda p: p != "",
            subprocess.check_output(
                ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                cwd=cwd,
                text=True,
                stderr=subprocess.DEVNULL,
            ).split("\n"),
        )
        if (Path(cwd) / p).exists()
    )
    add_to_db = {
        "ids": [],
        "documents": [],
        "metadatas": [],
    }
    for path in git_paths:
        try:

            document = get_document(path, cwd)
            checksum = hash_str(document)
            existing_record = len(get_db(cwd).get(checksum)["ids"]) > 0
            if refresh or not existing_record:
                if existing_record:
                    get_db(cwd).delete(checksum)
                # add new items to db (will generate embeddings)
                metadatas = {
                    "id": str(path), 
                    "type": "file", 
                    "path": str(path), 
                    "checksum": checksum, 
                    "active": False
                }
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(metadatas)
            checksums[path] = checksum
        except UnicodeDecodeError:  # Ignore non-text files
            pass
        except Exception as e:
            print(f"Error processing path {path}: {e}")
    if len(add_to_db["ids"]) > 0:
        get_db(cwd).add(**add_to_db)
    return checksums


class Hierarchy(Annotator):
    name = "hierarchy"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        cwd = Path(graph.graph["cwd"])
        checksums = get_active_checksums(cwd)
        files_checksum = hash_str("".join(sorted(checksums.values())))
        return graph.graph.get("files_checksum") == files_checksum

    async def annotate(self, old_graph: nx.MultiDiGraph, refresh: bool = False) -> nx.MultiDiGraph:
        """Build a graph of active files and directories with hierarchy edges."""
        cwd = Path(old_graph.graph["cwd"])
        checksums = get_active_checksums(cwd, refresh=refresh)
        files_checksum = hash_str("".join(sorted(checksums.values())))
        
        graph = nx.MultiDiGraph()
        graph.graph["cwd"] = str(cwd)
        edges_to_add = set()
        for path, checksum in checksums.items():
            # add db reecord
            node_id = str(path)
            db_record = get_db(cwd).get(checksum)
            record = db_record["metadatas"][0]
            graph.add_node(node_id, **record)
            # add hierarchy edges
            def _link_to_cwd(_path):
                _parent = str(_path.parent) if len(_path.parts) > 1 else "ROOT"
                edges_to_add.add((_parent, str(_path)))
                if _parent != "ROOT":
                    _link_to_cwd(_path.parent)
            _link_to_cwd(path)
        
        # Add directory nodes with checksums
        for (source, target) in edges_to_add:
            for node_id in (source, target):
                if node_id not in graph:
                    # add directories to graph (to link hierarchy) but not db
                    record = {"id": node_id, "type": "directory", "path": node_id}
                    graph.add_node(node_id, **record)
            graph.add_edge(source, target, type="hierarchy")
        
        graph.graph["files_checksum"] = files_checksum
        return graph
