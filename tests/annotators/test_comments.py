from textwrap import dedent
from ragdaemon.annotators.comment import CommentPosition

import pytest
from ragdaemon.context import ContextBuilder
from ragdaemon.daemon import Daemon

@pytest.mark.asyncio
async def test_comment_render(git_history, mock_db):
    daemon = Daemon(cwd=git_history)
    await daemon.update(refresh=True)

    context = ContextBuilder(daemon.graph, daemon.db)
    context.add_ref("src/operations.py")
    context.add_comment("src/operations.py", "What is this file for?", positioning=CommentPosition.File)
    context.add_comment("src/operations.py", "Thanks\nfor doing this",line=12,  positioning=CommentPosition.Above)
    context.add_comment("src/operations.py", "ackj", line=12, positioning=CommentPosition.Below)
    context.add_comment("src/operations.py", "Comment order preserved", line=12, positioning=CommentPosition.Below)
    context.add_comment("src/operations.py", "smart ->",line=12,  positioning=CommentPosition.Start)
    context.add_comment("src/operations.py", "<- idk",line=12,  positioning=CommentPosition.End)
    actual = context.render()
    assert (
        actual
        == dedent("""\
            src/operations.py
            What is this file for?
            --------------------------------------------------------------------------------
            1:import math
            2: #modified
            3: #modified
            4:def add(a, b): #modified
            5:    return a + b
            6:
            7:
            8:def subtract(a, b):
            9:return a - b #modified
            10:
            11:
            --------------------------------------------------------------------------------
            Thanks
            for doing this
            --------------------------------------------------------------------------------
            smart ->: 12:def multiply(a, b): <- idk
            --------------------------------------------------------------------------------
            ackj
            --------------------------------------------------------------------------------
            --------------------------------------------------------------------------------
            Comment order preserved
            --------------------------------------------------------------------------------
            13:    return a * b
            14:
            15:
            16:def divide(a, b):
            17:    return a / b
            18:
            19:
            20:def sqrt(a):
            21:    return math.sqrt(a)
            """
    ))
    context.remove_comments("src/operations.py")
    actual = context.render()
    assert (
        actual
        == dedent("""\
            src/operations.py
            1:import math
            2: #modified
            3: #modified
            4:def add(a, b): #modified
            5:    return a + b
            6:
            7:
            8:def subtract(a, b):
            9:return a - b #modified
            10:
            11:
            12:def multiply(a, b):
            13:    return a * b
            14:
            15:
            16:def divide(a, b):
            17:    return a / b
            18:
            19:
            20:def sqrt(a):
            21:    return math.sqrt(a)
            """
    ))
