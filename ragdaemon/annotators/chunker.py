from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator


class Chunker(Annotator):
    name = "chunker"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        # If all file nodes' chromadb records have "chunker"
        pass

    def annotate(self, graph: nx.MultiDiGraph, cwd: Path) -> nx.MultiDiGraph:
        """
        a. Iterate over file nodes without it (parallel)
            a. Run chunker
            b. Add result to file node's chromadb record
            c. Add/update dependent edges/nodes in graph
            d. Save updated edges/nodes to chroma
        (back to LEVEL 1)
        """
        pass
