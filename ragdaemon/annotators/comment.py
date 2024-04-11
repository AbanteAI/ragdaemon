from typing import Union, Dict
from dict2xml import dict2xml


NestedStrDict = Union[str, Dict[str, "NestedStrDict"]]


class Comment:
    def __init__(
        self,
        content: NestedStrDict,
    ):
        self.content = content

    def render(self) -> str:
        return dict2xml(self.content, wrap="comment", indent="    ")


def render_comments(comments: list[Comment]) -> str:
    return "\n".join(comment.render() for comment in comments)
