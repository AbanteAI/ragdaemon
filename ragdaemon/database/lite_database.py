from pathlib import Path
from typing import Any, Optional

from rank_bm25 import BM25Okapi

from ragdaemon.database.database import Database


def tokenize(document: str) -> list[str]:
    return document.split()


class LiteDB(Database):
    def __init__(self, db_path: Path, verbose: int = 0):
        self.db_path = db_path
        self.verbose = verbose
        self._collection = LiteCollection(self.verbose)

    def query(self, query: str, active_checksums: list[str]) -> list[dict]:
        return self._collection.query(query, active_checksums)


class LiteCollection:
    """A fast alternative to ChromaDB for testing (and anything else).

    Matches the chroma Collection API except:
    - No embeddings
    - In-memory
    - Query returns all distances=1
    """

    bm25: BM25Okapi
    bm25_index: list[str]

    def __init__(self, verbose: int = 0):
        self.data = dict[str, dict[str, Any]]()  # {id: {metadatas, document}}
        self.verbose = verbose

    def get(self, ids: list[str] | str, include: Optional[list[str]] = None) -> dict:
        if isinstance(ids, str):
            ids = [ids]
        output = {"ids": [], "metadatas": [], "documents": []}
        for id in ids:
            if id in self.data:
                output["ids"].append(id)
                output["metadatas"].append(self.data[id]["metadatas"])
                output["documents"].append(self.data[id]["document"])
        if include:
            output = {k: v for k, v in output.items() if k in include or k == "ids"}
        return output

    def count(self) -> int:
        return len(self.data)

    def update(self, ids: list[str] | str, metadatas: list[dict] | dict):
        ids = [ids] if isinstance(ids, str) else ids
        metadatas = [metadatas] if isinstance(metadatas, dict) else metadatas
        for checksum, metadata in zip(ids, metadatas):
            if checksum not in self.data:
                raise ValueError(f"Record {checksum} does not exist.")
            self.data[checksum]["metadatas"] = metadata

    def query(self, query: str, active_checksums: list[str]) -> list[dict]:
        scores = self.bm25.get_scores(tokenize(query))
        max_score = max(scores)
        if max_score > 0:
            # Normalize to [0, 1]
            scores = [score / max_score for score in scores]
        results = [
            {"checksum": id, "distance": 1 - score}
            for id, score in zip(self.bm25_index, scores)
            if id in active_checksums
        ]
        results = sorted(results, key=lambda x: x["distance"])
        return results

    def add(
        self,
        ids: list[str] | str,
        metadatas: list[dict] | dict,
        documents: list[str] | str,
    ) -> list[str]:
        ids = [ids] if isinstance(ids, str) else ids
        metadatas = [metadatas] if isinstance(metadatas, dict) else metadatas
        documents = [documents] if isinstance(documents, str) else documents
        for checksum, metadata, document in zip(ids, metadatas, documents):
            existing_metadata = self.data.get(checksum, {}).get("metadatas", {})
            metadata = {**existing_metadata, **metadata}
            self.data[checksum] = {"metadatas": metadata, "document": document}

        # Update BM25
        ids, documents = [], []
        for id, data in self.data.items():
            ids.append(id)
            documents.append(data["document"])
        self.bm25 = BM25Okapi([tokenize(document) for document in documents])
        self.bm25_index = ids

        return ids
