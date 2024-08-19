from typing import Optional

from psycopg2 import OperationalError
from spice import Spice
from sqlalchemy import select, func

from ragdaemon.database.database import Database
from ragdaemon.database.postgres import get_database_session_sync, DocumentMetadata

MAX_INPUTS_PER_CALL = 2048


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


class PGDB(Database):
    """Implementation of Database with embeddings search using PostgreSQL."""

    def __init__(
        self,
        spice_client: Spice,
        embedding_model: str | None = None,
        embedding_provider: Optional[str] = None,
        verbose: int = 0,
    ):
        self.verbose = verbose
        SessionLocal = get_database_session_sync()
        with SessionLocal() as session:
            query = select(func.count(DocumentMetadata.id))
            count = session.execute(query).scalar()
            if self.verbose > 0:
                print(f"Initialized PGDB with {count} documents.")

        # def embed_documents(self, input_texts: list[str]) -> list[list[float]]:
        # if not all(isinstance(item, str) for item in input_texts):
        #     raise RagdaemonError("SpiceEmbeddings only enabled for text files.")
        # # Embed in batches
        # n_batches = (len(input_texts) - 1) // MAX_INPUTS_PER_CALL + 1
        # output: list[list[float]] = []
        # for batch in range(n_batches):
        #     start = batch * MAX_INPUTS_PER_CALL
        #     end = min((batch + 1) * MAX_INPUTS_PER_CALL, len(input_texts))
        #     embeddings = spice_client.get_embeddings_sync(
        #         input_texts=input_texts[start:end],
        #         model=embedding_model,
        #         provider=embedding_provider,
        #     ).embeddings
        #     output.extend(embeddings)
        # return output

        # self.embed_documents = embed_documents

    @retry_on_exception()
    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: Optional[list[dict]] = None,
    ):
        if metadatas is None:
            metadatas = [{} for _ in range(len(ids))]
        # embeddings = self.embed_documents(documents)
        # metadatas = [{**meta, "embedding": emb} for meta, emb in zip(metadatas, embeddings)]
        SessionLocal = get_database_session_sync()
        with SessionLocal() as session:
            for id, metadata in zip(ids, metadatas):
                session.add(DocumentMetadata(id=id, **metadata))
            session.commit()

    @retry_on_exception()
    def update(self, ids: list[str], metadatas: list[dict]):
        SessionLocal = get_database_session_sync()
        with SessionLocal() as session:
            for id, metadata in zip(ids, metadatas):
                session.query(DocumentMetadata).filter(
                    DocumentMetadata.id == id
                ).update(metadata)
            session.commit()

    @retry_on_exception()
    def get(
        self, ids: list[str], include: Optional[list[str]] = None
    ) -> dict[str, list[str] | list[dict]]:
        SessionLocal = get_database_session_sync()
        with SessionLocal() as session:
            query = select(DocumentMetadata).filter(DocumentMetadata.id.in_(ids))
            result = session.execute(query).scalars().all()
            output: dict[str, list[str] | list[dict]] = {
                "ids": [doc.id for doc in result]
            }
            if include is None or "metadatas" in include:
                output["metadatas"] = [doc.to_dict(exclude=["id"]) for doc in result]
            return output

    @retry_on_exception()
    def query(self, query: str, active_checksums: list[str]) -> list[dict]:
        return [{"checksum": checksum, "distance": 1} for checksum in active_checksums]
