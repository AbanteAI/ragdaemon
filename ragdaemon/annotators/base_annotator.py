from pathlib import Path

import networkx as nx


class Annotator:
    name: str = "base_annotator"
    def __init__(self, cwd: Path, config: dict = {}):
        self.cwd = cwd
        self.config = config

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        raise NotImplementedError()

    def annotate(self, graph: nx.MultiDiGraph, cwd: Path) -> nx.MultiDiGraph:
        raise NotImplementedError()
