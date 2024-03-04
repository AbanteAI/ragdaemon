import pytest

from ragdaemon.daemon import Daemon


def get_message_chunk_set(message):  # Because order can vary
    chunks = message.split("\n\n")
    if len(chunks) > 0:
        for i in range(len(chunks) - 1):
            chunks[i] += "\n"



@pytest.mark.asyncio
async def test_daemon_get_context(cwd):
    # Full Context
    daemon = Daemon(cwd.resolve())
    await daemon.update()
    actual = daemon.get_context_message("test", max_tokens=1e6)
    
    with open("tests/data/context_message.txt", "r") as f:
        expected = f.read()
    assert get_message_chunk_set(actual) == get_message_chunk_set(expected)

    # Included Files
    actual = daemon.get_context_message(
        "test", include=["src/interface.py:11-12"], auto_tokens=0
    )
    assert (
        actual
        == """\
src/interface.py (user-included)
...
11:    match = re.match(r"(\d+)(\D)(\d+)", args.operation)
12:    if match is None:
...
"""
    )
