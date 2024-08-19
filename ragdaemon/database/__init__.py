import os  # noqa: F401
from typing import Optional

from spice import Spice

from ragdaemon.database.database import Database
from ragdaemon.database.lite_database import LiteDB

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


def get_db(
    spice_client: Spice,
    embedding_model: str | None = None,
    embedding_provider: Optional[str] = None,
    verbose: int = 0,
) -> Database:
    # if embedding_model is not None and "PYTEST_CURRENT_TEST" not in os.environ:
    #     try:
    #         db = PGDB(db_path=db_path, verbose=verbose)
    #         return db
    #     except Exception as e:
    #         if verbose > 1:
    #             print(
    #                 f"Failed to initialize Postgres Database: {e}. Falling back to LiteDB."
    #             )
    #         pass
    return LiteDB(verbose=verbose)
