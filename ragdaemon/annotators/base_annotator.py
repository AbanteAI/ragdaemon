from pathlib import Path

import networkx as nx


class Annotator:
    name: str = "base_annotator"
    def __init__(self):
        pass

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        raise NotImplementedError()

    async def annotate(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        raise NotImplementedError()
