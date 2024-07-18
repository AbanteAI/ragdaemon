from unittest.mock import AsyncMock

from ragdaemon.database import DEFAULT_EMBEDDING_MODEL, LiteDB, get_db


def test_mock_database():
    db = get_db(AsyncMock(), embedding_model=DEFAULT_EMBEDDING_MODEL)
    assert isinstance(db, LiteDB)
