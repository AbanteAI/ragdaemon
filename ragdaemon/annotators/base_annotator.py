import networkx as nx
from spice import Spice


class Annotator:
    name: str = "base_annotator"

    def __init__(self, verbose: bool = False, spice_client: Spice = None):
        self.verbose = verbose
        self.spice_client = spice_client
        pass

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        raise NotImplementedError()

    async def annotate(
        self, graph: nx.MultiDiGraph, refresh: bool = False
    ) -> nx.MultiDiGraph:
        raise NotImplementedError()
