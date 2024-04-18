from pathlib import Path
from typing import Optional

from ragdaemon.graph import KnowledgeGraph


class Database:
    embedding_model: str | None = None
    _collection = None  # Collection | LiteDB

    def __init__(self, cwd: Path, db_path: Path) -> None:
        raise NotImplementedError

    def __getattr__(self, name):
        """Delegate attribute access to the collection."""
        return getattr(self._collection, name)

    def query(self, query: str, active_checksums: list[str]) -> list[dict]:
        raise NotImplementedError

    def query_graph(
        self, query: str, graph: KnowledgeGraph, n: Optional[int] = None
    ) -> list[dict]:
        """Return documents, metadatas and distances, sorted, for nodes in the graph.

        Chroma's default search covers all records, including inactive ones, so we
        manually flag the active records, query them, and then unflag them.
        """
        active_checksums = [
            data["checksum"]
            for _, data in graph.nodes(data=True)
            if data and "checksum" in data
        ]
        results = self.query(query, active_checksums)
        if n:
            results = results[:n]
        return results
