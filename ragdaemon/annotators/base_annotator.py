import networkx as nx


class Annotator:
    name: str = "base_annotator"

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        pass

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        raise NotImplementedError()

    async def annotate(
        self, graph: nx.MultiDiGraph, refresh: bool = False
    ) -> nx.MultiDiGraph:
        raise NotImplementedError()
