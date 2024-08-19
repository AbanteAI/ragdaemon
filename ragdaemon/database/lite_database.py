from typing import Any, Optional, TypedDict

from rank_bm25 import BM25Okapi

from ragdaemon.database.database import Database


def tokenize(document: str) -> list[str]:
    return document.split()


class Document(TypedDict):
    checksum: str
    chunks: Optional[list[dict[str, str]]]
    summary: Optional[str]
    embedding: Optional[list[float]]


class LiteDB(Database):
    """A fast alternative to Embeddings DB for testing (and anything else)."""

    bm25: BM25Okapi
    bm25_index: list[str]

    def __init__(self, verbose: int = 0):
        self.verbose = verbose
        self.data = dict[str, dict[str, Any]]()  # {id: {metadatas, document}}

    def get(self, ids: list[str], include: Optional[list[str]] = None) -> dict:
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

    def update(self, ids: list[str], metadatas: list[dict]):
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
        ids: list[str],
        documents: list[str],
        metadatas: Optional[list[dict]] = None,
    ):
        if metadatas is None:
            metadatas = [{} for _ in range(len(ids))]
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
