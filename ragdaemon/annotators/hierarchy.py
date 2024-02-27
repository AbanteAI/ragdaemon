from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import get_db
from ragdaemon.utils import get_active_files, get_file_checksum, hash_str

def _link_to_cwd(path: Path, graph: nx.MultiDiGraph):
    """Recursively add "hierarchy" edges back to the cwd node"""
    parent = path.parent
    if len(parent.parts) == 0:  # Reached the root
        graph.add_edge("ROOT", str(path), type="hierarchy")
        return
    if str(parent) not in graph:  # Create directory path like os.mkdir
        graph.add_node(str(parent), path=str(parent), type="directory", id=str(parent))
        _link_to_cwd(parent, graph)
    graph.add_edge(str(parent), str(path), type="hierarchy")


class Hierarchy(Annotator):
    name = "hierarchy"
    description = "Build a graph of active files"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        # If any modified, created or deleted files
        active_files = get_active_files(self.cwd)
        checksums = {f: get_file_checksum(self.cwd / f) for f in active_files}
        return graph.graph.get("files_checksum") == hash_str(str(checksums))

    async def annotate(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        """Build a graph of active files and directories with hierarchy edges."""
        # Reset active database records (for search)
        for record in get_db()._db.values():
            record["active"] = False

        # Create an empty new graph
        new_graph = nx.MultiDiGraph()
        active_files = get_active_files(self.cwd)
        checksums = {f: get_file_checksum(self.cwd / f) for f in active_files}
        new_graph.graph["files_checksum"] = hash_str(str(checksums))

        # Add file nodes into the graph, starting with the cwd
        new_graph.add_node("ROOT", path=".", type="directory", id="ROOT")
        for file in active_files:
            checksum = checksums[file]
            # Get or create a database record for checksum, set it active (for search)
            record = get_db().get(checksum)
            if record:
                record["active"] = False
            else:
                record = {"id": str(file), "path": str(file)}
            record["checksum"] = checksum
            new_graph.add_node(record["id"], **record)
            _link_to_cwd(file, new_graph)
            record["active"] = True
            get_db().set(checksum, record)
        return new_graph
