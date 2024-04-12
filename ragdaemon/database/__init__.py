import os
from pathlib import Path

from spice import Spice
from spice.errors import SpiceError

from ragdaemon.database.chroma_database import ChromaDB
from ragdaemon.database.database import Database
from ragdaemon.database.lite_database import LiteDB
from ragdaemon.utils import mentat_dir_path

MAX_TOKENS_PER_EMBEDDING = 8192
DEFAULT_EMBEDDING_MODEL = "text-embedding-ada-002"


def get_db(cwd: Path, spice_client: Spice) -> Database:
    db_path = mentat_dir_path / "chroma"
    db_path.mkdir(parents=True, exist_ok=True)
    if "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            return ChromaDB(cwd=cwd, db_path=db_path, spice_client=spice_client)
        except SpiceError:
            pass
    return LiteDB(cwd=cwd, db_path=db_path)
