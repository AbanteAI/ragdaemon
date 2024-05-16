from pathlib import Path
from typing import Any, Iterable, Optional

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
        self,
        query: str,
        graph: KnowledgeGraph,
        n: Optional[int] = None,
        node_types: Iterable[str] = ("file", "chunk", "diff"),
    ) -> list[dict]:
        """Return documents, metadatas and distances, sorted, for nodes in the graph.

        Chroma's default search covers all records, including inactive ones, so we
        manually flag the active records, query them, and then unflag them.
        """
        checksum_index = {
            data["checksum"]: node
            for node, data in graph.nodes(data=True)
            if data and "checksum" in data and data["type"] in node_types
        }
        response = self.query(query, list(checksum_index.keys()))

        # Add (local) metadata to results
        results = list[dict[str, Any]]()
        for result in response:
            node = checksum_index[result["checksum"]]
            data = graph.nodes[node]
            result = {**result, **data}
            results.append(result)

        # Add exact-match multiplier
        for result in results:
            distance = result["distance"]
            type = result["type"]
            if type == "file":
                name = Path(result["id"]).name
            elif type == "chunk":
                name = result["id"].split(":")[1]
                if "." in name:
                    name = name.split(".")[-1]
            else:
                name = ""  # not applicable for diffs

            if query in name:
                distance *= 0.5
            elif query in result["id"]:
                distance *= 0.75
            elif query in result["document"]:
                distance *= 0.9

            result["distance"] = distance
        results = sorted(results, key=lambda x: x["distance"])

        if n:
            results = results[:n]
        return results
