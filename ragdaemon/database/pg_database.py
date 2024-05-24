import json
import os
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from typing_extensions import override

from ragdaemon.database.lite_database import LiteCollection, LiteDB


class Base(DeclarativeBase):
    pass


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id: Mapped[str] = mapped_column(primary_key=True)
    chunks_llm: Mapped[str]


class Engine:
    def __init__(self):
        database = "ragdaemon"
        host = os.environ.get("RAGDAEMON_DB_ENDPOINT", None)
        port = os.environ.get("RAGDAEMON_DB_PORT", 5432)
        username = os.environ.get("RAGDAEMON_DB_USERNAME", None)
        password = os.environ.get("RAGDAEMON_DB_PASSWORD", None)

        if host is None or username is None or password is None:
            raise ValueError(
                "Missing ragdaemon environment variables: cannot use PGDB."
            )

        url = f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
        self.engine = create_engine(url)
        print("Connected to PGDB.")

    def migrate(self):
        if input(
            "Migrating will clear the database. ALL DATA WILL BE LOST. Proceed (Y/n)? "
        ).lower().strip() in [
            "",
            "y",
        ]:
            Base.metadata.drop_all(self.engine)
            Base.metadata.create_all(self.engine)
            print("PGDB migrated successfully.")

    def add_document_metadata(self, id: str, metadata: Dict):
        with Session(self.engine) as session:
            serialized_metadata = {}
            for k, v in metadata.items():
                serialized_metadata[k] = json.dumps(v)
            metadata_object = DocumentMetadata(id=id, **serialized_metadata)
            session.add(metadata_object)
            session.commit()

    def update_document_metadata(self, id: str, metadata: Dict):
        with Session(self.engine) as session:
            metadata_object = session.get(DocumentMetadata, id)
            assert (
                metadata_object is not None
            ), f"No document metadata found with id {id}!"
            for k, v in metadata.items():
                setattr(metadata_object, k, json.dumps(v))
            session.commit()

    def get_document_metadata(self, id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            metadata_object = session.get(DocumentMetadata, id)
        if metadata_object is None:
            return metadata_object

        serialized_metadata = metadata_object.__dict__.copy()
        del serialized_metadata["_sa_instance_state"]
        metadata = {}
        for k, v in serialized_metadata:
            metadata[k] = json.loads(v)
        return metadata


class PGDB(LiteDB):
    def __init__(self, cwd: Path, db_path: Path):
        super().__init__(cwd, db_path)
        self._collection = PGCollection()


class PGCollection(LiteCollection):
    """Wraps a LiteDB and adds/gets targeted fields from a remote Postgres Database."""

    def __init__(self, *args, fields: list[str] = ["chunks_llm"], **kwargs):
        super().__init__(*args, **kwargs)
        self.engine = Engine()
        self.fields = fields

    @override
    def update(self, ids: list[str] | str, metadatas: list[dict] | dict):
        for id, metadata in zip(ids, metadatas):
            self.engine.update_document_metadata(id, metadata)
        super().update(ids, metadatas)

    @override
    def add(
        self,
        ids: list[str] | str,
        metadatas: list[dict] | dict,
        documents: list[str] | str,
    ) -> list[str]:
        for id, metadata in zip(ids, metadatas):
            remote_metadata = self.engine.get_document_metadata(id)
            if remote_metadata is not None:
                metadata.update(remote_metadata)
        return super().add(ids, metadatas, documents)


if __name__ == "__main__":
    Engine().migrate()
