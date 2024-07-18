from __future__ import annotations

from typing import Optional

from spice import Spice

from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.io import IO


class Annotator:
    name: str = "base_annotator"

    def __init__(
        self,
        io: IO,
        verbose: int = 0,
        spice_client: Optional[Spice] = None,
        pipeline: Optional[dict[str, Annotator]] = None,
    ):
        self.io = io
        self.verbose = verbose
        self.spice_client = spice_client
        pass

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        raise NotImplementedError()

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: str | bool = False
    ) -> KnowledgeGraph:
        raise NotImplementedError()
