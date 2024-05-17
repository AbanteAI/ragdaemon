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
        """
        Since we add many different versions of each file to Chroma, we can't do a
        straightforward query, because it'd return multiple version of the same file.

        The best workaround I've found for this is using the 'active' flag in metadata.
        The downside is that it requires 2 additional calls to the database each time:
        one to set it, another to unset it. The extra time is negligible for local DBs
        and hopefully not unreasonable for remote.

        There's a third "extra" call to validate the active_checksums. If we don't do
        this it will still function properly but it will print a lot of warnings.
        """
        valid_checksums = self._collection.get(ids=active_checksums, include=[])["ids"]
        # Flag active records
        updates = {
            "ids": valid_checksums,
            "metadatas": [{"active": True} for _ in valid_checksums],
        }
        self._collection.update(**updates)
        # Query
        response = self._collection.query(
            query_texts=query,
            where={"active": True},
            n_results=len(valid_checksums),
            include=["distances"],
        )
        # Remove flags
        updates = {
            "ids": valid_checksums,
            "metadatas": [{"active": False} for _ in valid_checksums],
        }
        self._collection.update(**updates)
        if response is None or response["distances"] is None:
            return []
        # Parse results. Return results for the 'first query' only
        results = [
            {"checksum": id, "distance": distance}
            for id, distance in zip(response["ids"][0], response["distances"][0])
        ]
        results = sorted(results, key=lambda x: x["distance"])
        return results
