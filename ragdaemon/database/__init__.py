import os
from pathlib import Path
from typing import Optional

from spice import Spice
from spice.errors import SpiceError

from ragdaemon.database.chroma_database import ChromaDB, remove_add_to_db_duplicates
from ragdaemon.database.database import Database
from ragdaemon.database.lite_database import LiteDB
from ragdaemon.utils import mentat_dir_path

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


def get_db(
    cwd: Path,
    spice_client: Spice,
    embedding_model: str | None = None,
    embedding_provider: Optional[str] = None,
) -> Database:
    db_path = mentat_dir_path / "chroma"
    db_path.mkdir(parents=True, exist_ok=True)
    if embedding_model is not None and "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            db = ChromaDB(
                cwd=cwd,
                db_path=db_path,
                spice_client=spice_client,
                embedding_model=embedding_model,
                embedding_provider=embedding_provider,
            )
            # In case the api key is wrong, try to embed something to trigger an error.
            _ = db.add(ids="test", documents="test doc")
            db.delete(ids="test")
            return db
        except Exception:
            pass
    return LiteDB(cwd=cwd, db_path=db_path)
