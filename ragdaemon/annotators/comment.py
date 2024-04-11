from enum import Enum
from typing import Optional


class CommentPosition(Enum):
    File = "file"
    Above = "above"
    Below = "below"
    Start = "start"
    End = "end"


LINE_DELIMITER = 80 * "-"


class Comment:
    def __init__(
        self,
        content: str,
        positioning: CommentPosition = CommentPosition.Below,
        line: Optional[int] = None,
        end_line: Optional[int] = None,
        start_delimiter: Optional[str] = None,
        end_delimiter: Optional[str] = None,
    ):
        assert (
            line or positioning == CommentPosition.File
        ), f"Comment positioned via {positioning} must set line number"
        assert line or not end_line, "Comments with end_line must set line"
        assert "\n" not in content or positioning not in [
            CommentPosition.Start,
            CommentPosition.End,
        ], "Start and end comments must be one line"
        self.content = content
        self.positioning = positioning
        self.line = line
        self.end_line = end_line
        if not start_delimiter:
            match self.positioning:
                case CommentPosition.File:
                    self.start_delimiter = ""
                case CommentPosition.Above:
                    self.start_delimiter = LINE_DELIMITER + "\n"
                case CommentPosition.Below:
                    self.start_delimiter = "\n" + LINE_DELIMITER + "\n"
                case CommentPosition.Start:
                    self.start_delimiter = ""
                case CommentPosition.End:
                    self.start_delimiter = " "
        else:
            self.start_delimiter = start_delimiter
        if not end_delimiter:
            match self.positioning:
                case CommentPosition.File:
                    self.end_delimiter = "\n" + LINE_DELIMITER + "\n"
                case CommentPosition.Above:
                    self.end_delimiter = "\n" + LINE_DELIMITER + "\n"
                case CommentPosition.Below:
                    self.end_delimiter = "\n" + LINE_DELIMITER
                case CommentPosition.Start:
                    self.end_delimiter = ": "
                case CommentPosition.End:
                    self.end_delimiter = ""
        else:
            self.end_delimiter = end_delimiter

    def render(self, line_content: Optional[str] = None) -> str:
        assert (
            line_content or self.positioning == CommentPosition.File
        ), "Non-file level comments need a string to annotate"
        assert (
            not line_content or self.positioning != CommentPosition.File
        ), "File level comments don't annotate a line"
        wrapped_content = self.start_delimiter + self.content + self.end_delimiter
        match self.positioning:
            case CommentPosition.File:
                return wrapped_content
            case CommentPosition.Above:
                return wrapped_content + line_content
            case CommentPosition.Below:
                return line_content + wrapped_content
            case CommentPosition.Start:
                return wrapped_content + line_content
            case CommentPosition.End:
                return line_content + wrapped_content


def render_comments(comments: list[Comment], line_content: Optional[str] = None) -> str:
    # Sort comments so that start and end comments are processed first
    comments = sorted(
        comments,
        key=lambda c: (
            c.positioning not in [CommentPosition.Start, CommentPosition.End],
            comments.index(c),
        ),
    )
    for comment in comments:
        line_content = comment.render(line_content)
    return line_content
