import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
import networkx as nx


api_key = os.environ.get("OPENAI_API_KEY")


_client = None
_collection = None
def get_db(cwd):
    db_path = Path(cwd) / ".ragdaemon" / "chroma"
    global _client
    global _collection
    if _collection is None:
        if _client is None:
            _client = chromadb.PersistentClient(path=str(db_path))
        _collection = _client.get_or_create_collection(
            name="ragdaemon",
            embedding_function=OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small",
            )
        )
    return _collection


def query_graph(query: str, graph: nx.MultiDiGraph) -> list[dict]:
    """Return documents, metadatas and distances, sorted, for nodes in the graph.
    
    Chroma's default search covers all records, including inactive ones, so we
    manually flag the active records, query them, and then unflag them.
    """
    cwd = graph.graph["cwd"]
    metadatas = get_db(cwd).get([
        data["checksum"] for _, data in graph.nodes(data=True) if "checksum" in data
    ])["metadatas"]
    metadatas = [{ **data, "active": True } for data in metadatas]
    get_db(cwd).update(ids=[m["checksum"] for m in metadatas], metadatas=metadatas)
    response = get_db(cwd).query(
        query_texts=query,
        where={"active": True},
        n_results=len(metadatas),
    )
    metadatas = [{ **data, "active": False } for data in metadatas]
    get_db(cwd).update(ids=[m["checksum"] for m in metadatas], metadatas=metadatas)
    results = [
        { **data, "document": document, "distance": distance } 
        for data, document, distance in zip(
            response["metadatas"][0], response["documents"][0], response["distances"][0])
    ]
    results = sorted(results, key=lambda x: x["distance"])
    return results
