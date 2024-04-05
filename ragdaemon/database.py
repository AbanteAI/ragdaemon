import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

import chromadb
import networkx as nx

from ragdaemon.llm import embedding_function
from ragdaemon.utils import mentat_dir_path, parse_path_ref

MAX_TOKENS_PER_EMBEDDING = 8192


class LiteDB:
    def __init__(self):
        self.db = dict[str, dict[str, Any]]()

    def get(self, ids: list[str] | str) -> dict:
        if isinstance(ids, str):
            ids = [ids]
        output = {"ids": [], "metadatas": [], "documents": []}
        for id in ids:
            if id in self.db:
                output["ids"].append(id)
                output["metadatas"].append(self.db[id]["metadatas"])
                output["documents"].append(self.db[id]["document"])
        return output

    def count(self) -> int:
        return len(self.db)

    def update(self, ids: list[str] | str, metadatas: list[dict] | dict):
        ids = [ids] if isinstance(ids, str) else ids
        metadatas = [metadatas] if isinstance(metadatas, dict) else metadatas
        for checksum, metadata in zip(ids, metadatas):
            if checksum not in self.db:
                raise ValueError(f"Record {checksum} does not exist.")
            self.db[checksum]["metadatas"] = metadata

    def query(self, query_texts: list[str] | str, where: dict, n_results: int) -> dict:
        # Select active/filtered records
        records = [{"id": id, **data} for id, data in self.db.items()]
        if where:
            filtered_records = list[dict[str, Any]]()
            for record in records:
                selected = all(record.get("metadatas", {}).get(key) == value for key, value in where.items())
                if selected:
                    filtered_records.append(record)
            records = filtered_records
        if not query_texts:
            return {
                "ids": [r["id"] for r in records],
                "metadatas": [r["metadatas"] for r in records],
                "documents": [r["document"] for r in records],
                "distances": [0] * len(records),
            }
        if isinstance(query_texts, str):
            query_texts = [query_texts]

        # Pull out some fields to string match against
        strings_to_compare = dict[str, list[tuple[str, float]]]()
        for record in records:
            stc = list[tuple]()  # string, category_weight
            data = record["metadatas"]
            if data["type"] == "diff" and ":" in data["ref"]:
                path = Path(path.split(":")[1])
            else:
                path, _ = parse_path_ref(data["ref"])
            stc.append((path.name, 2))
            stc.append((path.as_posix(), 1))
            stc.append((record["document"], 0.5))
            strings_to_compare[record["id"]] = stc

        output = {"ids": [], "metadatas": [], "documents": [], "distances": []}
        for text in query_texts:
            # Compare each query text against each records' strings
            distances = list[tuple[str, float]]()
            for id, stc in strings_to_compare.items():
                score = 0
                for string, weight in stc:
                    if string in text or text in string:
                        score += weight
                distance = 10 if not score else 1 / score
                distances.append((id, distance))
            # Sort by distance
            ids, distances = zip(*sorted(distances, key=lambda x: x[1]))
            output["ids"].append(ids)
            output["metadatas"].append([self.db[id]["metadatas"] for id in ids])
            output["documents"].append([self.db[id]["document"] for id in ids])
            output["distances"].append(distances)

        return output

    def upsert(
        self,
        ids: list[str] | str,
        metadatas: list[dict] | dict,
        documents: list[str] | str,
    ) -> list[str]:
        ids = [ids] if isinstance(ids, str) else ids
        metadatas = [metadatas] if isinstance(metadatas, dict) else metadatas
        documents = [documents] if isinstance(documents, str) else documents
        for checksum, metadata, document in zip(ids, metadatas, documents):
            existing_metadata = self.db.get(checksum, {}).get("metadatas", {})
            metadata = {**existing_metadata, **metadata}
            self.db[checksum] = {"metadatas": metadata, "document": document}
        return ids


_collection: ContextVar = ContextVar("_collection", default=None)


def set_db(cwd: Path):
    global _collection

    if "PYTEST_CURRENT_TEST" in os.environ:
        _collection.set(LiteDB())
        return

    db_path = mentat_dir_path / "chroma"
    db_path.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(db_path))
    name = f"ragdaemon-{Path(cwd).name}"
    _collection.set(
        _client.get_or_create_collection(
            name=name,
            embedding_function=embedding_function,
        )
    )


def get_db(cwd: Path) -> chromadb.Collection:
    global _collection
    collection = _collection.get()
    if collection is None:
        set_db(cwd)
        collection = _collection.get()
    return collection


def query_graph(
    query: str, graph: nx.MultiDiGraph, n: Optional[int] = None
) -> list[dict]:
    """Return documents, metadatas and distances, sorted, for nodes in the graph.

    Chroma's default search covers all records, including inactive ones, so we
    manually flag the active records, query them, and then unflag them.
    """
    cwd = graph.graph["cwd"]
    metadatas = get_db(cwd).get(
        [data["checksum"] for _, data in graph.nodes(data=True) if "checksum" in data]
    )["metadatas"]
    metadatas = [{**data, "active": True} for data in metadatas]
    if len(metadatas) == 0:
        return []
    get_db(cwd).update(ids=[m["checksum"] for m in metadatas], metadatas=metadatas)
    response = get_db(cwd).query(
        query_texts=query,
        where={"active": True},
        n_results=len(metadatas),
    )
    metadatas = [{**data, "active": False} for data in metadatas]
    get_db(cwd).update(ids=[m["checksum"] for m in metadatas], metadatas=metadatas)
    results = [
        {**data, "document": document, "distance": distance}
        for data, document, distance in zip(
            response["metadatas"][0], response["documents"][0], response["distances"][0]
        )
    ]
    results = sorted(results, key=lambda x: x["distance"])
    if n:
        results = results[:n]
    return results
