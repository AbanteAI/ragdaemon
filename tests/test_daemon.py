import pytest

from ragdaemon.daemon import Daemon, default_annotators


def get_message_chunk_set(message):  # Because order can vary
    chunks = message.split("\n\n")
    if len(chunks) > 0:
        for i in range(len(chunks) - 1):
            chunks[i] += "\n"


@pytest.mark.asyncio
async def test_daemon_get_context(cwd):
    # Full Context
    annotators = default_annotators()
    del annotators["diff"]
    daemon = Daemon(cwd.resolve(), annotators=annotators)
    await daemon.update()
    actual = daemon.get_context("test", max_tokens=1000).render(use_tags=True)

    with open("tests/data/context_message.txt", "r") as f:
        expected = f.read()
    assert get_message_chunk_set(actual) == get_message_chunk_set(expected)

    # Included Files
    context = daemon.get_context("test")
    context.add_ref("src/interface.py:11-12", tags=["user-included"])
    actual = daemon.get_context("test", context_builder=context, auto_tokens=0).render(
        use_tags=True
    )
    assert (
        actual
        == """\
src/interface.py (user-included)
...
11:    match = re.match(r"(\\d+)(\\D)(\\d+)", args.operation)
12:    if match is None:
...
"""
    )
