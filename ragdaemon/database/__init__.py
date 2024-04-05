import os
from contextvars import ContextVar
from pathlib import Path

from ragdaemon.database.database import Database
from ragdaemon.database.chroma_database import ChromaDB
from ragdaemon.database.lite_database import LiteDB
from ragdaemon.utils import mentat_dir_path

MAX_TOKENS_PER_EMBEDDING = 8192


_db: ContextVar = ContextVar("_db", default=None)


def set_db(cwd: Path):
    global _db
    db_path = mentat_dir_path / "chroma"
    db_path.mkdir(parents=True, exist_ok=True)
    db_class = LiteDB if "PYTEST_CURRENT_TEST" in os.environ else ChromaDB
    _db.set(db_class(cwd=cwd, db_path=db_path))


def get_db(cwd: Path) -> Database:
    global _db
    db = _db.get()
    if db is None:
        set_db(cwd)
        db = _db.get()
    return db
