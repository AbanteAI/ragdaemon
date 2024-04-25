from pathlib import Path
from typing import Any

from ragdaemon.database.database import Database


class LiteDB(Database):
    def __init__(self, cwd: Path, db_path: Path):
        self.cwd = cwd
        self.db_path = db_path
        self._collection = LiteCollection()

    def query(self, query: str, active_checksums: list[str]) -> list[dict]:
        response = self._collection.query(query, active_checksums)
        results = [
            {**data, "document": document, "distance": distance}
            for data, document, distance in zip(
                response["metadatas"][0],
                response["documents"][0],
                response["distances"][0],
            )
        ]
        results = sorted(results, key=lambda x: x["distance"])
        return results


class LiteCollection:
    """A fast alternative to ChromaDB for testing (and anything else).

    Matches the chroma Collection API except:
    - No embeddings
    - In-memory
    - A basic hand-coded search algo
    """

    def __init__(self):
        self.data = dict[str, dict[str, Any]]()  # {id: {metadatas, document}}

    def get(self, ids: list[str] | str) -> dict:
        if isinstance(ids, str):
            ids = [ids]
        output = {"ids": [], "metadatas": [], "documents": []}
        for id in ids:
            if id in self.data:
                output["ids"].append(id)
                output["metadatas"].append(self.data[id]["metadatas"])
                output["documents"].append(self.data[id]["document"])
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

    def query(self, query: str, active_checksums: list[str]) -> dict[str, list[Any]]:
        # Select active/filtered records
        records = [
            {"id": k, **v} for k, v in self.data.items() if k in active_checksums
        ]
        return {
            "ids": [[r["id"] for r in records]],
            "metadatas": [[r["metadatas"] for r in records]],
            "documents": [[r["document"] for r in records]],
            "distances": [[1] * len(records)],
        }

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
            existing_metadata = self.data.get(checksum, {}).get("metadatas", {})
            metadata = {**existing_metadata, **metadata}
            self.data[checksum] = {"metadatas": metadata, "document": document}
        return ids
