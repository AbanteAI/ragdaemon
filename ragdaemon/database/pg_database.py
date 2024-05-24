from collections import defaultdict
from pathlib import Path

from ragdaemon.database.lite_database import LiteDB, LiteCollection


class PGDB(LiteDB):
    def __init__(self, cwd: Path, db_path: Path):
        super().__init__(cwd, db_path)
        self._collection = PGCollection()


class PGCollection(LiteCollection):
    """Wraps a LiteDB and adds/gets targeted fields from a remote Postgres Database."""

    def __init__(self, *args, fields: list[str] = ["chunks_llm"], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields = fields

    def update(self, ids: list[str] | str, metadatas: list[dict] | dict):
        remote_records = defaultdict(dict)
        for id, metadata in zip(ids, metadatas):
            for k, v in metadata.items():
                if k in self.fields:
                    remote_records[id][k] = v
        # TODO: Update remote records
        super().update(ids, metadatas)

    def add(
        self,
        ids: list[str] | str,
        metadatas: list[dict] | dict,
        documents: list[str] | str,
    ) -> list[str]:
        # TODO: Fetch remote records for ids
        remote_records = {}
        for id, metadata in zip(ids, metadatas):
            if id in remote_records:
                metadata.update(remote_records[id])
        return super().add(ids, metadatas, documents)
