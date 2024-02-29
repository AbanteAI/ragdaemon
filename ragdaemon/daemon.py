import json
from pathlib import Path

import networkx as nx

from ragdaemon.annotators import Hierarchy, Chunker, LayoutHierarchy
from ragdaemon.utils import ragdaemon_dir
from ragdaemon.database import get_db



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
            self.graph.graph["cwd"] = str(cwd)
            print(f"Initialized empty graph.")

        self.pipeline = [
            Hierarchy(),
            Chunker(),
            LayoutHierarchy(),
        ]

    def save(self):
        """Saves the graph to disk."""
        data = nx.readwrite.json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"refreshed knowledge graph saved to {self.graph_path}")

    async def refresh(self):
        """Iteratively build the knowledge graph"""
        for annotator in self.pipeline:
            if not annotator.is_complete(self.graph):
                self.graph = await annotator.annotate(self.graph)
                self.save()

    def search(self, query: str):
        return get_db().query(query_texts=query)
