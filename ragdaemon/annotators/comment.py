from typing import Union, Dict, Optional
from dict2xml import dict2xml


NestedStrDict = Union[str, Dict[str, "NestedStrDict"]]


class Comment:
    def __init__(
        self,
        content: NestedStrDict,
        wrap: Optional[str] = "comment",
    ):
        self.content = content
        self.wrap = wrap

    def render(self) -> str:
        return dict2xml(self.content, wrap=self.wrap, indent="    ")


def render_comments(comments: list[Comment]) -> str:
    return "\n".join(comment.render() for comment in comments)
