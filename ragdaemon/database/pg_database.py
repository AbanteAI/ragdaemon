import json
import os
from collections import defaultdict
from typing import Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from typing_extensions import override

from ragdaemon.database.lite_database import LiteCollection, LiteDB


class Base(DeclarativeBase):
    pass


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id: Mapped[str] = mapped_column(primary_key=True)
    # We serialize whatever we get, which can be 'null', so we need Optional
    chunks: Mapped[Optional[str]]


def retry_on_exception(retries: int = 3, exceptions={OperationalError}):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    print(f"Caught exception: {e}")
                    if i == retries - 1:
                        raise e

        return wrapper

    return decorator


class Engine:
    def __init__(self, verbose: int = 0):
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
        if verbose > 1:
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

    @retry_on_exception()
    def add_document_metadata(self, ids: str | list[str], metadatas: Dict | list[Dict]):
        ids = ids if isinstance(ids, list) else [ids]
        metadatas = metadatas if isinstance(metadatas, list) else [metadatas]
        if len(ids) != len(metadatas):
            raise ValueError("ids and metadatas must have the same length.")
        with Session(self.engine) as session:
            for id, metadata in zip(ids, metadatas):
                serialized_metadata = {}
                for k, v in metadata.items():
                    if not isinstance(v, str):
                        v = json.dumps(v)
                    serialized_metadata[k] = v
                metadata_object = DocumentMetadata(id=id, **serialized_metadata)
                session.add(metadata_object)
            session.commit()

    @retry_on_exception()
    def update_document_metadata(
        self, ids: str | list[str], metadatas: Dict | list[Dict]
    ):
        ids = ids if isinstance(ids, list) else [ids]
        metadatas = metadatas if isinstance(metadatas, list) else [metadatas]
        if len(ids) != len(metadatas):
            raise ValueError("ids and metadatas must have the same length.")
        with Session(self.engine) as session:
            for id, metadata in zip(ids, metadatas):
                metadata_object = session.get(DocumentMetadata, id)
                if metadata_object is None:
                    metadata_object = DocumentMetadata(id=id)
                    session.add(metadata_object)
                for k, v in metadata.items():
                    if not isinstance(v, str):
                        v = json.dumps(v)
                    setattr(metadata_object, k, v)
            session.commit()

    @retry_on_exception()
    def get_document_metadata(self, ids: str | list[str]) -> Dict[str, Dict]:
        if not isinstance(ids, list):
            ids = [ids]
        with Session(self.engine) as session:
            metadata_objects = (
                session.query(DocumentMetadata)
                .filter(DocumentMetadata.id.in_(ids))
                .all()
            )
        result = dict[str, Dict]()
        for object in metadata_objects:
            id = object.id
            serialized_metadata = object.__dict__.copy()
            del serialized_metadata["_sa_instance_state"]
            del serialized_metadata["id"]
            result[id] = dict(serialized_metadata)  # Deserialization logic is elsewhere
        return result


class PGDB(LiteDB):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._collection = PGCollection(self.verbose)


class PGCollection(LiteCollection):
    """Wraps a LiteDB and adds/gets targeted fields from a remote Postgres Database."""

    def __init__(self, *args, fields: list[str] = ["chunks"], **kwargs):
        super().__init__(*args, **kwargs)
        self.engine = Engine(self.verbose)
        self.fields = fields

    @override
    def update(self, ids: list[str] | str, metadatas: list[dict] | dict):
        remote_records = defaultdict(dict)
        for id, metadata in zip(ids, metadatas):
            for k, v in metadata.items():
                if k in self.fields:
                    remote_records[id][k] = v
        self.engine.update_document_metadata(
            ids=list(remote_records.keys()), metadatas=list(remote_records.values())
        )
        super().update(ids, metadatas)

    @override
    def add(
        self,
        ids: list[str] | str,
        metadatas: list[dict] | dict,
        documents: list[str] | str,
    ) -> list[str]:
        remote_metadatas = self.engine.get_document_metadata(ids)
        for id, metadata in zip(ids, metadatas):
            if id in remote_metadatas:
                metadata.update(remote_metadatas[id])
        return super().add(ids, metadatas, documents)

    @override
    def get(
        self,
        ids: list[str] | str,
        include: list[str] | None = None,
    ):
        response = super().get(ids, include)
        response_ids = response.get("ids", [])
        if response_ids and include is not None and "metadatas" in include:
            remote_metadatas = self.engine.get_document_metadata(response_ids)
            for id, metadata in zip(
                response.get("ids", []), response.get("metadatas", [])
            ):
                if id in remote_metadatas:
                    metadata.update(remote_metadatas[id])
        return response


if __name__ == "__main__":
    Engine().migrate()
