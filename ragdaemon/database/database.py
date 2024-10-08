from pathlib import Path
from typing import Any, Iterable, Optional

from ragdaemon.graph import KnowledgeGraph


class Database:
    embedding_model: str | None = None

    def __init__(self, db_path: Path) -> None:
        raise NotImplementedError

    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: Optional[list[dict]] = None,
    ):
        # NOTE: In the past we had issues with duplicates. LiteDB doesn't mind, but PGDB might.
        raise NotImplementedError

    def update(self, ids: list[str], metadatas: list[dict]):
        # NOTE: Same as above re: duplicates
        raise NotImplementedError

    def get(self, ids: list[str], include: Optional[list[str]] = None) -> dict:
        raise NotImplementedError

    def query(self, query: str, active_checksums: set[str]) -> list[dict]:
        raise NotImplementedError

    def query_graph(
        self,
        query: str,
        graph: KnowledgeGraph,
        n: Optional[int] = None,
        node_types: Iterable[str] = ("file", "chunk", "diff"),
    ) -> list[dict]:
        """Return documents, metadatas and distances, sorted, for nodes in the graph."""
        # If query is empty, searching DB will raise "RuntimeError('Cannot return the
        # results in a contigious 2D array. Probably ef or M is too small')"
        if not query:
            results = [
                {**data, "distance": 1}
                for _, data in graph.nodes(data=True)
                if data and "checksum" in data and data["type"] in node_types
            ]
            if n:
                results = results[:n]
            return results

        checksum_index = {
            data["checksum"]: node
            for node, data in graph.nodes(data=True)
            if data and "checksum" in data and data["type"] in node_types
        }
        response = self.query(query, set(checksum_index.keys()))

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
            # Replaced by BM25
            # elif query in result["document"]:
            #     distance *= 0.9

            result["distance"] = distance
        results = sorted(results, key=lambda x: x["distance"])

        if n:
            results = results[:n]
        return results
