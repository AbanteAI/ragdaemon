import asyncio
import pytest

from ragdaemon.daemon import Daemon
from ragdaemon.database import get_db


@pytest.mark.asyncio
async def test_daemon_get_context(cwd):
    daemon = Daemon(cwd.resolve())
    await daemon.refresh()

    nodes = [data for _, data in daemon.graph.nodes(data=True) if "checksum" in data]
    response = get_db(cwd).get(ids=[n["checksum"] for n in nodes])
    data = [
        { **metadatas, "document": document } 
        for metadatas, document in zip(response["metadatas"], response["documents"])
    ]
    context_message = daemon.render_context_message(data)
    with open('context_message.txt', 'w') as f:
        f.write(context_message)

