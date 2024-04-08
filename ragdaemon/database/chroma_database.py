from pathlib import Path

import chromadb
from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings
from spice import Spice

from ragdaemon.database.database import Database


MAX_INPUTS_PER_CALL = 2048


class ChromaDB(Database):
    def __init__(self, cwd: Path, db_path: Path, spice_client: Spice) -> None:
        self.cwd = cwd
        self.db_path = db_path
        self.model = spice_client._default_embeddings_model.name

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
                    embeddings = spice_client.get_embeddings_sync(input_texts=inputs)
                    outputs.extend(embeddings)
                return outputs

        embedding_function = SpiceEmbeddingFunction()

        _client = chromadb.PersistentClient(path=str(db_path))
        name = f"ragdaemon-{self.cwd.name}-{self.model}"
        self._collection = _client.get_or_create_collection(
            name=name,
            embedding_function=embedding_function,
        )
