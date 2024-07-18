import os  # noqa: F401
from typing import Optional

from spice import Spice

from ragdaemon.database.chroma_database import (
    # ChromaDB,
    remove_add_to_db_duplicates,  # noqa: F401
    remove_update_db_duplicates,  # noqa: F401
)
from ragdaemon.database.database import Database

# from ragdaemon.database.chroma_database import ChromaDB
from ragdaemon.database.lite_database import LiteDB

# from ragdaemon.database.pg_database import PGDB
from ragdaemon.utils import mentat_dir_path

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


def get_db(
    spice_client: Spice,
    embedding_model: str | None = None,
    embedding_provider: Optional[str] = None,
    verbose: int = 0,
) -> Database:
    db_path = mentat_dir_path / "chroma"
    db_path.mkdir(parents=True, exist_ok=True)
    # if embedding_model is not None and "PYTEST_CURRENT_TEST" not in os.environ:
    #     try:
    #         # db = ChromaDB(
    #         #     db_path=db_path,
    #         #     spice_client=spice_client,
    #         #     embedding_model=embedding_model,
    #         #     embedding_provider=embedding_provider,
    #         #     verbose=verbose,
    #         # )
    #         # # In case the api key is wrong, try to embed something to trigger an error.
    #         # _ = db.add(ids="test", documents="test doc")
    #         # db.delete(ids="test")
    #         db = PGDB(db_path=db_path, verbose=verbose)
    #         return db
    #     except Exception as e:
    #         if verbose > 1:
    #             print(
    #                 f"Failed to initialize Postgres Database: {e}. Falling back to LiteDB."
    #             )
    #         pass
    return LiteDB(db_path=db_path, verbose=verbose)
