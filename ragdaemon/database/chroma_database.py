from pathlib import Path
from timeit import default_timer
from typing import TYPE_CHECKING, Optional

from spice import Spice
from spice.spice import Model, Provider

from ragdaemon.database.database import Database

MAX_INPUTS_PER_CALL = 2048

if TYPE_CHECKING:
    from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings


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
        from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings

        class SpiceEmbeddingFunction(EmbeddingFunction[Embeddable]):
            def __call__(self, input_texts: Embeddable) -> Embeddings:
                if isinstance(input_texts, str):
                    input_texts = [input_texts]
                # Embed in batches
                _inputs = input_texts
                outputs = list[list[float]]()
                while _inputs:
                    inputs = _inputs[:MAX_INPUTS_PER_CALL]
                    _inputs = _inputs[MAX_INPUTS_PER_CALL:]
                    embeddings = spice_client.get_embeddings_sync(
                        input_texts=inputs, model=model, provider=provider
                    ).embeddings
                    outputs.extend(embeddings)
                return outputs

        embedding_function = SpiceEmbeddingFunction()

        _client = chromadb.PersistentClient(path=str(db_path))
        name = f"ragdaemon-{self.cwd.name}-{self.model}"
        self._collection = _client.get_or_create_collection(
            name=name,
            embedding_function=embedding_function,
        )
