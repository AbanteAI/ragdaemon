import json
from pathlib import Path

import chromadb

from ragdaemon.utils import ragdaemon_dir


db_path = ragdaemon_dir / "chroma"


_client = None
_collection = None
def get_db():
    global _client
    global _collection
    if _collection is None:
        if _client is None:
            _client = chromadb.PersistentClient(path=str(db_path))
        _collection = _client.get_or_create_collection(name="ragdaemon")
    return _collection
