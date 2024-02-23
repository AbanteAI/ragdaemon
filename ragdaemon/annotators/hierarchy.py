from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator


class Hierarchy(Annotator):
    name = "hierarchy"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        # If nodes and last-modified in active files matches graph
        pass

    def annotate(self, graph: nx.MultiDiGraph, cwd: Path) -> nx.MultiDiGraph:
        """
        a. set active=False on all chromadb entries
        b. Iterate over active files
            i. Get checksum/last_modified
            ii. Get complete record from chroma or add
            iii. Generate hierarchical edges if missing
            iv. Add node and edges to graph
            v. Save to chroma with active=True
        """
        pass
