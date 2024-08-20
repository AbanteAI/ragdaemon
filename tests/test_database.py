from unittest.mock import AsyncMock

from ragdaemon.database import LiteDB, get_db
from ragdaemon.utils import DEFAULT_EMBEDDING_MODEL


def test_mock_database():
    db = get_db(AsyncMock(), embedding_model=DEFAULT_EMBEDDING_MODEL)
    assert isinstance(db, LiteDB)
