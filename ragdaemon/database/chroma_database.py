from pathlib import Path

import chromadb
from chromadb.api import Collection
from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings
from spice import SpiceEmbeddings

from ragdaemon.database.database import Database


def _get_chroma_collection(
    cwd: Path, db_path: Path, embedding_model: str, embedding_provider: str
) -> Collection:
    embedding_client = SpiceEmbeddings(provider=embedding_provider)

    class RagdaemonEmbeddingFunction(EmbeddingFunction[Embeddable]):
        def __call__(self, input: Embeddable) -> Embeddings:
            return embedding_client.get_embeddings(input, embedding_model)

    embedding_function = RagdaemonEmbeddingFunction()

    _client = chromadb.PersistentClient(path=str(db_path))
    name = f"ragdaemon-{Path(cwd).name}"
    return _client.get_or_create_collection(
        name=name,
        embedding_function=embedding_function,
    )


class ChromaDB(Database):
    def __init__(
        self, cwd: Path, db_path: Path, embedding_model: str, embedding_provider: str
    ) -> None:
        self.cwd = cwd
        self.db_path = db_path
        self._collection = _get_chroma_collection(
            cwd, db_path, embedding_model, embedding_provider
        )
