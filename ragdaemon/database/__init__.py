import os
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from spice import SpiceError

from ragdaemon.database.database import Database
from ragdaemon.database.chroma_database import ChromaDB
from ragdaemon.database.lite_database import LiteDB
from ragdaemon.utils import mentat_dir_path

MAX_TOKENS_PER_EMBEDDING = 8192
DEFAULT_EMBEDDING_MODEL = "text-embedding-ada-002"
DEFAULT_EMBEDDING_PROVIDER = "openai"


_db: ContextVar = ContextVar("_db", default=None)


def set_db(
    cwd: Path,
    embedding_model: Optional[str] = None,
    embedding_provider: Optional[str] = None,
):
    global _db
    db_path = mentat_dir_path / "chroma"
    db_path.mkdir(parents=True, exist_ok=True)
    if "PYTEST_CURRENT_TEST" not in os.environ and embedding_provider is not None:
        try:
            embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL
            embedding_provider = embedding_provider or DEFAULT_EMBEDDING_PROVIDER
            _db.set(
                ChromaDB(
                    cwd=cwd,
                    db_path=db_path,
                    embedding_model=embedding_model,
                    embedding_provider=embedding_provider,
                )
            )
            return
        except SpiceError:
            pass
    _db.set(LiteDB(cwd=cwd, db_path=db_path))


def get_db(cwd: Path) -> Database:
    global _db
    db = _db.get()
    if db is None:
        set_db(cwd)
        db = _db.get()
    return db
