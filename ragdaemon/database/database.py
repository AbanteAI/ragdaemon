from pathlib import Path
from typing import Optional

import networkx as nx


class Database:
    _collection = None  # Collection | LiteDB

    def __init__(self, cwd: Path, db_path: Path) -> None:
        raise NotImplementedError

    def __getattr__(self, name):
        """Delegate attribute access to the collection."""
        return getattr(self._collection, name)

    def query_graph(
        self, query: str, graph: nx.MultiDiGraph, n: Optional[int] = None
    ) -> list[dict]:
        """Return documents, metadatas and distances, sorted, for nodes in the graph.

        Chroma's default search covers all records, including inactive ones, so we
        manually flag the active records, query them, and then unflag them.
        """
        metadatas = self._collection.get(
            [
                data["checksum"]
                for _, data in graph.nodes(data=True)
                if "checksum" in data
            ]
        )["metadatas"]
        metadatas = [{**data, "active": True} for data in metadatas]
        if len(metadatas) == 0:
            return []
        self._collection.update(
            ids=[m["checksum"] for m in metadatas], metadatas=metadatas
        )
        response = self._collection.query(
            query_texts=query,
            where={"active": True},
            n_results=len(metadatas),
        )
        metadatas = [{**data, "active": False} for data in metadatas]
        self._collection.update(
            ids=[m["checksum"] for m in metadatas], metadatas=metadatas
        )
        results = [
            {**data, "document": document, "distance": distance}
            for data, document, distance in zip(
                response["metadatas"][0],
                response["documents"][0],
                response["distances"][0],
            )
        ]
        results = sorted(results, key=lambda x: x["distance"])
        if n:
            results = results[:n]
        return results
