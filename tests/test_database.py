from unittest.mock import AsyncMock

from ragdaemon.database import DEFAULT_EMBEDDING_MODEL, LiteDB, get_db


def test_mock_database(cwd):
    db = get_db(cwd, AsyncMock(), model=DEFAULT_EMBEDDING_MODEL)
    assert isinstance(db, LiteDB)
