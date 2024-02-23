from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator


class LayoutTSNE(Annotator):
    name = "layout_tsne"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        # If all nodes have "layout.tsne"
        pass

    def annotate(self, graph: nx.MultiDiGraph, cwd: Path) -> nx.MultiDiGraph:
        """
        a. Regenerate x/y/z for all nodes
        b. Update all nodes
        c. Save to chroma
        """
        pass
