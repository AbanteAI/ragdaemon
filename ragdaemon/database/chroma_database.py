from pathlib import Path
from typing import cast, TYPE_CHECKING, Optional

from spice import Spice

from ragdaemon.database.database import Database
from ragdaemon.errors import RagdaemonError

MAX_INPUTS_PER_CALL = 2048

if TYPE_CHECKING:
    from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings, Metadata, GetResult # noqa: F401


class ChromaDB(Database):
    def __init__(
        self,
        cwd: Path,
        db_path: Path,
        spice_client: Spice,
        model: str,
        provider: Optional[str] = None,
    ) -> None:
        self.cwd = cwd
        self.db_path = db_path
        self.model = model

        import chromadb  # Imports are slow so do it lazily
        from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings  # noqa: F811

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
                        model=model,
                        provider=provider,
                    ).embeddings
                    output.extend(embeddings)
                return output

        embedding_function = SpiceEmbeddingFunction()

        _client = chromadb.PersistentClient(path=str(db_path))
        name = f"ragdaemon-{self.cwd.name}-{self.model}"
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
        # Parse results
        data = response["metadatas"]
        documents = response["documents"]
        distances = response["distances"]
        if not data or not documents or not distances:
            raise RagdaemonError("Missing field in response.")
        results = [
            {**metadata, "document": document, "distance": distance}
            for metadata, document, distance in zip(metadatas, documents, distances)
        ]
        results = sorted(results, key=lambda x: x["distance"])
        return results
