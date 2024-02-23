from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator


class Summarizer(Annotator):
    name = "summarizer"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        # If all nodes have "summary" field
        pass

    def annotate(self, graph: nx.MultiDiGraph, cwd: Path) -> nx.MultiDiGraph:
        """
        a. Iterate over nodes without it (parallel)
            a. Run summarizer
            b. Add summary to node in graph
            c. Add result to node's chromadb record
        """
        pass
