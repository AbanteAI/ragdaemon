import json
from pathlib import Path

import networkx as nx

from ragdaemon.annotators import (
    Hierarchy, 
    LayoutHierarchy, 
    Chunker, 
    Summarizer, 
    LayoutCallgraph, 
    LayoutTSNE,
)


class Daemon:
    """Build and maintain a searchable knowledge graph of codebase."""
    def __init__(self, cwd: Path, config: dict = {}):
        self.cwd = cwd
        self.config = config
        self.up_to_date = False
        self.error = None

        # Load or initialize graph
        self.graph_path = cwd / ".ragdaemon" / "graph.json"
        self.graph_path.parent.mkdir(exist_ok=True)
        if self.graph_path.exists():
            with open(self.graph_path, "r") as f:
                data = json.load(f)
                self.graph = nx.readwrite.json_graph.node_link_graph(data)
        else:
            self.graph = nx.MultiDiGraph()

        self.save()

        # Iteratively build graph by adding annotations to the graph object.
        # Save the graph to disk after each annotation.
        self.pipeline = [
            
            # Build a graph of active files
            Hierarchy(cwd, config.get(Hierarchy.name, {})),

            # Add 3d force-directed layout of file structure
            LayoutHierarchy(cwd, config.get(LayoutHierarchy.name, {})),
            
            # # Convert files into chunks w/ calls, add to graph
            # Chunker(cwd, config.get(Chunker.name, {})),
            
            # # Add 3d force-directed layout of call graph
            # LayoutCallgraph(cwd, config.get(LayoutCallgraph.name, {})),
            
            # # Generate text summary of each node in context
            # Summarizer(cwd, config.get(Summarizer.name, {})),
            
            # # Add tsne of embedded summaries
            # LayoutTSNE(cwd, config.get(LayoutTSNE.name, {})),
        ]

    def save(self):
        """Saves the graph to disk."""
        data = nx.readwrite.json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=4)

    async def refresh(self):
        """Iteratively updates graph by calling itself until graph is fully annotated."""
        for annotator in self.pipeline:
            try:
                if not annotator.is_complete(self.graph):
                    self.graph = await annotator.annotate(self.graph)
                    self.save()
            except Exception as e:
                self.error = e
                print(f"Error in {annotator.name}: {e}")
                break
    
    async def search(self, query: str, limit: None, tokens: None):
        """Searches the graph for a given query."""
        pass
