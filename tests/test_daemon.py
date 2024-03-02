import asyncio
import pytest

from ragdaemon.daemon import Daemon
from ragdaemon.database import get_db


@pytest.mark.asyncio
async def test_daemon_get_context(cwd):
    daemon = Daemon(cwd.resolve())
    await daemon.refresh()
    actual = daemon.get_context_message("test", max_tokens=1e6)
    with open('tests/data/context_message.txt', 'r') as f:
        expected = f.read()
    assert actual == expected
