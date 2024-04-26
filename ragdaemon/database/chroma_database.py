from pathlib import Path
from typing import TYPE_CHECKING, Optional, cast

from spice import Spice

from ragdaemon.database.database import Database
from ragdaemon.errors import RagdaemonError

MAX_INPUTS_PER_CALL = 2048

if TYPE_CHECKING:
    from chromadb.api.types import (
        GetResult,
        Metadata,
    )


class ChromaDB(Database):
    def __init__(
        self,
        cwd: Path,
        db_path: Path,
        spice_client: Spice,
        embedding_model: str,
        embedding_provider: Optional[str] = None,
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

        _client = chromadb.PersistentClient(path=str(db_path))
        name = f"ragdaemon-{self.cwd.name}-{self.embedding_model}"
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
