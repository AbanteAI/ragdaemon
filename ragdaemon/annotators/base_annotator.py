from typing import Optional

from spice import Spice

from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph


class Annotator:
    name: str = "base_annotator"

    def __init__(self, verbose: bool = False, spice_client: Optional[Spice] = None):
        self.verbose = verbose
        self.spice_client = spice_client
        pass

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        raise NotImplementedError()

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        raise NotImplementedError()
