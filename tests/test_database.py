from unittest.mock import AsyncMock

from ragdaemon.database import get_db, set_db, LiteDB


def test_mock_database(cwd):
    set_db(cwd, AsyncMock())
    db = get_db(cwd)
    assert isinstance(db, LiteDB)
