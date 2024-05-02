import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

import dotenv
from chromadb.config import Settings
from spice import Spice

from ragdaemon import __version__
from ragdaemon.database.database import Database
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import basic_auth

MAX_INPUTS_PER_CALL = 2048

if TYPE_CHECKING:
    from chromadb.api.types import (
        GetResult,
        Metadata,
    )


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


class ChromaDB(Database):
    def __init__(
        self,
        cwd: Path,
        db_path: Path,
        spice_client: Spice,
        embedding_model: str,
        embedding_provider: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        self.cwd = cwd
        self.db_path = db_path
        self.embedding_model = embedding_model

        import chromadb  # Imports are slow so do it lazily
        from chromadb.api.types import (
            Embeddable,
            EmbeddingFunction,
            Embeddings,
        )

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
            if verbose:
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
        # Flag active records
        result: GetResult = self._collection.get(active_checksums)
        metadatas: Optional[list[Metadata]] = result["metadatas"]
        if not metadatas or len(metadatas) == 0:
            return []
        updates = {"ids": [], "metadatas": []}
        for metadata in metadatas:
            updates["ids"].append(metadata["checksum"])
            updates["metadatas"].append({**metadata, "active": True})
        self._collection.update(**updates)
        # Query
        response = self._collection.query(
            query_texts=query,
            where={"active": True},
            n_results=len(metadatas),
        )
        # Remove flags
        updates["metadatas"] = [{**metadata, "active": False} for metadata in metadatas]
        self._collection.update(**updates)
        # Parse results. Return results for the 'first query' only
        if (
            response is None
            or response["metadatas"] is None
            or response["documents"] is None
            or response["distances"] is None
        ):
            return []
        _metadatas = response["metadatas"][0]
        _documents = response["documents"][0]
        _distances = response["distances"][0]
        results = [
            {**m, "document": do, "distance": di}
            for m, do, di in zip(_metadatas, _documents, _distances)
        ]
        results = sorted(results, key=lambda x: x["distance"])
        return results
