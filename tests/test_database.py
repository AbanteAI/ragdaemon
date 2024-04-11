from unittest.mock import AsyncMock

from ragdaemon.database import get_db, LiteDB


def test_mock_database(cwd):
    db = get_db(cwd, AsyncMock())
    assert isinstance(db, LiteDB)
