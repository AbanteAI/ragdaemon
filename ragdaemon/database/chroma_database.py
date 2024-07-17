import os
from pathlib import Path
from typing import Any, Optional, cast

import dotenv
from spice import Spice

from ragdaemon import __version__
from ragdaemon.database.database import Database
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import basic_auth

MAX_INPUTS_PER_CALL = 2048


def remove_add_to_db_duplicates(
    ids: list[str], documents: list[str], metadatas: list[dict]
) -> dict[str, Any]:
    seen = set()
    output = {"ids": [], "documents": [], "metadatas": []}
    for id, document, metadata in zip(ids, documents, metadatas):
        if id not in seen:
            output["ids"].append(id)
            output["documents"].append(document)
            output["metadatas"].append(metadata)
            seen.add(id)
    return output


def remove_update_db_duplicates(
    ids: list[str], metadatas: list[dict]
) -> dict[str, Any]:
    seen = set()
    output = {"ids": [], "metadatas": []}
    for id, metadata in zip(ids, metadatas):
        if id not in seen:
            output["ids"].append(id)
            output["metadatas"].append(metadata)
            seen.add(id)
    return output


class ChromaDB(Database):
    def __init__(
        self,
        db_path: Path,
        spice_client: Spice,
        embedding_model: str,
        embedding_provider: Optional[str] = None,
        verbose: int = 0,
    ) -> None:
        self.db_path = db_path
        self.embedding_model = embedding_model
        self.verbose = verbose

        import chromadb  # Imports are slow so do it lazily
        from chromadb.api.types import (
            Embeddable,
            EmbeddingFunction,
            Embeddings,
        )
        from chromadb.config import Settings

        class SpiceEmbeddingFunction(EmbeddingFunction[Embeddable]):
            def __call__(self, input_texts: Embeddable) -> Embeddings:
                if not all(isinstance(item, str) for item in input_texts):
                    raise RagdaemonError("SpiceEmbeddings only enabled for text files.")
                input_texts = cast(list[str], input_texts)
                # Embed in batches
                n_batches = (len(input_texts) - 1) // MAX_INPUTS_PER_CALL + 1
                output: Embeddings = []
                for batch in range(n_batches):
                    start = batch * MAX_INPUTS_PER_CALL
                    end = min((batch + 1) * MAX_INPUTS_PER_CALL, len(input_texts))
                    embeddings = spice_client.get_embeddings_sync(
                        input_texts=input_texts[start:end],
                        model=embedding_model,
                        provider=embedding_provider,
                    ).embeddings
                    output.extend(embeddings)
                return output

        embedding_function = SpiceEmbeddingFunction()

        dotenv.load_dotenv()

        try:
            host = os.environ["CHROMA_SERVER_HOST"]
            port = int(os.environ.get("CHROMA_SERVER_HTTP_PORT", 443))
            username = os.environ["CHROMA_SERVER_USERNAME"]
            password = os.environ["CHROMA_SERVER_PASSWORD"]
            _client = chromadb.HttpClient(
                host=host,
                port=port,
                ssl=port == 443,
                headers={"Authorization": basic_auth(username, password)},
                settings=Settings(allow_reset=True, anonymized_telemetry=False),
            )
        except KeyError:
            if self.verbose > 0:
                print(
                    "No Chroma HTTP client environment variables found. Defaulting to PersistentClient."
                )
            _client = chromadb.PersistentClient(path=str(db_path))

        minor_version = ".".join(__version__.split(".")[:2])
        name = f"ragdaemon-{minor_version}-{self.embedding_model}"
        self._collection = _client.get_or_create_collection(
            name=name,
            embedding_function=embedding_function,
        )

    def query(self, query: str, active_checksums: list[str]) -> list[dict]:
        response = self._collection.query(
            query_texts=query,
            where={"checksum": {"$in": active_checksums}},  # type: ignore
            n_results=len(active_checksums),
            include=["distances"],
        )
        ids = response["ids"]
        distances = response["distances"]
        if not ids or not distances:
            return []
        results = [
            {"checksum": id, "distance": distance}
            for id, distance in zip(ids[0], distances[0])
        ]
        results = sorted(results, key=lambda x: x["distance"])
        return results
