from ragdaemon.database import get_db, set_db, LiteDB


def test_mock_database(cwd):
    set_db(cwd)
    db = get_db(cwd)
    assert isinstance(db, LiteDB)
