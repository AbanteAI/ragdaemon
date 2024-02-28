import json
import os
import subprocess
from pathlib import Path

import networkx as nx

from ragdaemon.utils import hash_str, ragdaemon_dir
from ragdaemon.database import get_db
from ragdaemon.viz.force_directed import fruchterman_reingold_3d


class Daemon:
    """Build and maintain a searchable knowledge graph of codebase."""

    def __init__(self, cwd: Path, config: dict = {}):
        self.cwd = cwd
        self.config = config
        self.up_to_date = False
        self.error = None

        # Load or setup db
        count = get_db().count()
        print(f"Initialized database with {count} records.")

        # Load or initialize graph
        self.graph_path = ragdaemon_dir / "graph.json"
        self.graph_path.parent.mkdir(exist_ok=True)
        if self.graph_path.exists():
            with open(self.graph_path, "r") as f:
                data = json.load(f)
                self.graph = nx.readwrite.json_graph.node_link_graph(data)
                print(f"Loaded graph with {self.graph.number_of_nodes()} nodes.")
        else:
            self.graph = nx.MultiDiGraph()
            print(f"Initialized empty graph.")

    def save(self):
        """Saves the graph to disk."""
        data = nx.readwrite.json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"reefreshed knowledge graph saved to {self.graph_path}")

    async def refresh(self):
        """Iteratively updates graph by calling itself until graph is fully annotated."""
        # Determine current state
        git_paths = set(  # All non-ignored and untracked files
            Path(os.path.normpath(p))
            for p in filter(
                lambda p: p != "",
                subprocess.check_output(
                    ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                    cwd=self.cwd,
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).split("\n"),
            )
            if Path(self.cwd / p).exists()
        )
        checksums: dict[Path: str] = {}
        for path in git_paths:
            try:
                # could cache checksum by (path, last_updated) to save reads
                with open(self.cwd / path, "r") as f:
                    text = f.read()  
                document = f"{path}\n{text}"
                checksum = hash_str(document)
                if len(get_db().get(checksum)["ids"]) == 0:
                    # add new items to db (will generate embeddings)
                    metadatas = {
                        "id": str(path), 
                        "type": "file", 
                        "path": str(path), 
                        "checksum": checksum, 
                        "active": False
                    }
                    get_db().add(ids=checksum, documents=document, metadatas=metadatas)
                checksums[path] = checksum
            except UnicodeDecodeError:  # Ignore non-text files
                pass
            except Exception as e:
                print(f"Error processing path {path}: {e}")
        
        # Rebuild files if missing
        files_checksum = hash_str("".join(sorted(checksums.values())))
        if self.graph.graph.get("files_checksum") != files_checksum:        
            # Build graph and load from / add to db
            print(f"Refreshing file graph...")
            self.graph = nx.MultiDiGraph()
            edges_to_add = set()
            for path, checksum in checksums.items():
                # add db reecord
                node_id = str(path)
                db_record = get_db().get(checksum)
                record = db_record["metadatas"][0]
                self.graph.add_node(node_id, **record)
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
                    if node_id not in self.graph:
                        # add directories to graph (to link hierarchy) but not db
                        record = {"id": node_id, "type": "directory", "path": node_id}
                        self.graph.add_node(node_id, **record)
                self.graph.add_edge(source, target, type="hierarchy")
            self.graph.graph["files_checksum"] = files_checksum

        # Recalculate positions (save to graph only, not db)
        if not all(
            data.get("layout", {}).get("hierarchy")
            for _, data in self.graph.nodes(data=True)
        ):
            print(f"Generating 3d layout for {self.graph.number_of_nodes()} nodes")
            pos = fruchterman_reingold_3d(self.graph)
            for node_id, coordinates in pos.items():
                if "layout" not in self.graph.nodes[node_id]:
                    self.graph.nodes[node_id]["layout"] = {}
                self.graph.nodes[node_id]["layout"]["hierarchy"] = coordinates

        self.save()

    def search(self, query: str):
        
        return get_db().query(query_texts=query)
