from textwrap import dedent

import pytest
from ragdaemon.context import ContextBuilder, NestedStrDict
from ragdaemon.daemon import Daemon


@pytest.mark.asyncio
async def test_comment_render(git_history, mock_db):
    daemon = Daemon(cwd=git_history)
    await daemon.update(refresh=True)

    context = ContextBuilder(daemon.graph, daemon.db)
    context.add_ref("src/operations.py")
    context.add_comment(
        "src/operations.py", {"comment": "What is this file for?"}, tags=["test-flag"]
    )
    context.add_comment(
        "src/operations.py",
        {"comment": {"author": "bot", "content": "test"}},
        line=10,
        tags=["test-flag2"],
    )
    context.add_comment(
        "src/operations.py",
        {"comment": {"author": "bot", "content": "Two comments on one line"}},
        line=10,
    )
    nested_comment: NestedStrDict = {
        "author": "replier",
        "content": "Look replies are easy!",
    }
    context.add_comment(
        "src/operations.py",
        {"author": "bot", "content": "hello", "replies": nested_comment},
        line=20,
    )
    context.add_comment("src/operations.py", "Comments can just be strings", line=12)
    actual = context.render()
    assert actual == dedent("""\
            src/operations.py
            <comment>What is this file for?</comment>
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
            <comment>
                <author>bot</author>
                <content>test</content>
            </comment>
            <comment>
                <author>bot</author>
                <content>Two comments on one line</content>
            </comment>
            11:
            12:def multiply(a, b):
            Comments can just be strings
            13:    return a * b
            14:
            15:
            16:def divide(a, b):
            17:    return a / b
            18:
            19:
            20:def sqrt(a):
            <author>bot</author>
            <content>hello</content>
            <replies>
                <author>replier</author>
                <content>Look replies are easy!</content>
            </replies>
            21:    return math.sqrt(a)
            """)
    context.remove_comments("src/operations.py", tags=["test-flag"])
    actual = context.render()
    assert actual == dedent("""\
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
            <comment>
                <author>bot</author>
                <content>test</content>
            </comment>
            <comment>
                <author>bot</author>
                <content>Two comments on one line</content>
            </comment>
            11:
            12:def multiply(a, b):
            Comments can just be strings
            13:    return a * b
            14:
            15:
            16:def divide(a, b):
            17:    return a / b
            18:
            19:
            20:def sqrt(a):
            <author>bot</author>
            <content>hello</content>
            <replies>
                <author>replier</author>
                <content>Look replies are easy!</content>
            </replies>
            21:    return math.sqrt(a)
            """)
    context.remove_comments("src/operations.py")
    actual = context.render()
    assert actual == dedent("""\
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
            """)
