from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional, Union

from dict2xml import dict2xml
from ragdaemon.annotators.diff import parse_diff_id
from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import get_document, hash_str, parse_path_ref

NestedStrDict = Union[str, Dict[str, "NestedStrDict"]]


class Comment:
    def __init__(
        self,
        content: NestedStrDict,
        tags: list[str] = [],
    ):
        self.content = content
        self.tags = tags

    def render(self) -> str:
        return dict2xml(self.content, indent="    ")


def render_comments(comments: list[Comment]) -> str:
    return "\n".join(comment.render() for comment in comments)


class ContextBuilder:
    """Renders items from a graph into an llm-readable string."""

    def __init__(self, graph: KnowledgeGraph, db: Database, verbose: bool = False):
        self.graph = graph
        self.db = db
        self.verbose = verbose
        self.context = dict[
            str, dict[str, Any]
        ]()  # {path: {lines, tags, document, diff}}

    def copy(self):
        duplicate = ContextBuilder(self.graph, self.db, self.verbose)
        duplicate.context = deepcopy(self.context)
        return duplicate

    def __add__(self, other: ContextBuilder) -> ContextBuilder:
        duplicate = self.copy()
        for path_str, data in other.context.items():
            if path_str not in duplicate.context:
                duplicate.context[path_str] = data
            else:
                duplicate.context[path_str]["lines"].update(data["lines"])
                duplicate.context[path_str]["tags"].update(data["tags"])
                duplicate.context[path_str]["diffs"].update(data["diffs"])
                for line, comments in data["comments"].items():
                    duplicate.context[path_str]["comments"].setdefault(line, []).extend(
                        comments
                    )
        return duplicate

    def _add_path(self, path_str: str):
        """Create a new record in the context for the given path."""
        document = None
        if path_str in self.graph:
            checksum = self.graph.nodes[path_str]["checksum"]
            document = self.db.get(checksum)["documents"][0]
            if document.endswith("[TRUNCATED]"):
                document = None
        if document is None:  # Truncated or deleted
            try:
                # Could be an ignored file, in which case load it into graph/db
                # TODO: Add ignored files to the graph/database
                cwd = Path(self.graph.graph["cwd"])
                document = get_document(path_str, cwd, type="file")
            except FileNotFoundError:
                # Or could be deleted but have a diff
                document = f"{path_str}\n[DELETED]"
            checksum = hash_str(document)
        message = {
            "lines": set(),
            "tags": set(),
            "document": document,
            "diffs": set(),
            "comments": dict[int, list[Comment]](),
        }
        self.context[path_str] = message

    def add_id(self, node_id: str, tags: list[str] = []):
        """Add the given id to the context."""
        if node_id not in self.graph.nodes:
            raise ValueError(f"Node {node_id} not found in graph.")
        ref = self.graph.nodes[node_id].get("ref")
        if not ref:
            raise ValueError(f"Node {node_id} has no ref.")
        self.add_ref(ref, tags)

    def add_ref(self, path_ref: str, tags: list[str] = []):
        """Manually include path_refs"""
        path, lines = parse_path_ref(path_ref)
        path_str = path.as_posix()
        if path_str not in self.context:
            self._add_path(path_str)
        self.context[path_str]["tags"].update(tags)
        if not lines:
            document = self.context[path_str]["document"]
            lines = list(range(1, len(document.splitlines())))
        self.context[path_str]["lines"].update(lines)

    def add_diff(self, id: str):
        """Take a diff id and add to context"""
        _, path, _ = parse_diff_id(id)
        if not path:  # e.g. diff 'parent' nodes
            return
        path_str = path.as_posix()
        if path_str not in self.context:
            self._add_path(path_str)
        self.context[path_str]["diffs"].add(id)
        self.context[path_str]["tags"].add("diff")

    def add_comment(
        self,
        path_str: str,
        comment: NestedStrDict,
        line: Optional[int] = None,
        tags: list[str] = [],
    ):
        path_str = Path(path_str).as_posix()
        if not self.context.get(path_str):
            self._add_path(path_str)
        if not line:
            line = 0  # file-level comment
        self.context[path_str]["comments"].setdefault(line, []).append(
            Comment(
                content=comment,
                tags=tags,
            )
        )

    def remove_comments(self, path_str: str, tags: list[str] = []):
        if path_str not in self.context:
            if self.verbose:
                print(f"Warning: no matching message found for {path_str}.")
            return
        if tags:
            for line, comments in self.context[path_str]["comments"].items():
                self.context[path_str]["comments"][line] = [
                    comment for comment in comments if not set(tags) & set(comment.tags)
                ]
        else:
            self.context[path_str]["comments"] = dict[int, list[Comment]]()

    def remove_ref(self, ref: str, tags: list[str] = []):
        """Remove the given id from the context."""
        path, lines = parse_path_ref(ref)
        path_str = path.as_posix()
        if path_str not in self.context:
            if self.verbose:
                print(f"Warning: no matching message found for {path_str}.")
            return
        if lines:
            self.context[path_str]["lines"] -= lines
        else:
            self.context[path_str]["lines"] = set()
        if tags:
            self.context[path_str]["tags"] -= set(tags)
        if not self.context[path_str]["lines"] and not self.context[path_str]["diffs"]:
            del self.context[path_str]
        return ref

    def remove_diff(self, id: str):
        """Remove the given id from the context."""
        _, path, _ = parse_diff_id(id)
        if not path:  # e.g. diff 'parent' nodes
            return
        path_str = path.as_posix()
        if path_str not in self.context:
            if self.verbose:
                print(f"Warning: no matching message found for {path_str}.")
            return
        self.context[path_str]["diffs"].remove(id)
        self.context[path_str]["tags"].remove("diff")
        if not self.context[path_str]["lines"] and not self.context[path_str]["diffs"]:
            del self.context[path_str]
        return id

    def render(self, use_xml: bool = False, use_tags: bool = False) -> str:
        """Return a formatted context message for the given nodes."""
        output = ""
        for path_str, data in self.context.items():
            if output:
                output += "\n"

            if use_tags and data["tags"]:
                tags = f" ({', '.join(sorted(data['tags']))})"
            else:
                tags = ""

            if use_xml:
                output += f"<{path_str}>{tags}\n"
            else:
                output += f"{path_str}{tags}\n"

            if 0 in data["comments"]:
                output += render_comments(data["comments"][0]) + "\n"
            if data["lines"]:
                file_lines = data["document"].splitlines()
                last_rendered = 0
                for line in sorted(data["lines"]):
                    if line - last_rendered > 1:
                        output += "...\n"
                    line_content = f"{line}:{file_lines[line]}"
                    if line in data["comments"]:
                        line_content += "\n" + render_comments(data["comments"][line])
                    output += line_content + "\n"
                    last_rendered = line
                if last_rendered < len(file_lines) - 1:
                    output += "...\n"
            if data["diffs"]:
                output += self.render_diffs(data["diffs"])
            if use_xml:
                output += f"</{path_str}>\n"
        return output

    def render_diffs(self, ids: set[str]) -> str:
        output = ""
        diff_str, _, _ = parse_diff_id(next(iter(ids)))
        git_command = "--git diff"
        if diff_str != "DEFAULT":
            git_command += f" {diff_str}"
        output += f"{git_command}\n"
        for id in sorted(ids):
            checksum = self.graph.nodes[id]["checksum"]
            document = self.db.get(checksum)["documents"][0]
            # TODO: Add line numbers
            without_git_command = "\n".join(document.splitlines()[1:])
            output += without_git_command + "\n"
        return output

    def to_refs(self) -> list[str]:
        """Return a list of path:interval,interval for everything in current context."""
        refs = dict[str, str]()
        for path, data in self.context.items():
            if len(data["lines"]) == 0:
                continue
            elif len(data["lines"]) == data["document"].splitlines():
                refs[path] = ""
                continue
            segments = []
            current_segment = ""
            last_line = 0
            for line in sorted(data["lines"]):
                if line - last_line > 1:
                    current_segment += f"-{last_line}"
                    segments.append(current_segment)
                    current_segment = ""
                if not current_segment:
                    current_segment = str(line)
                last_line = line
            if current_segment:
                current_segment += f"-{last_line}"
                segments.append(current_segment)
            refs[path] = ",".join(segments)
        return [f"{path}:{ref}" for path, ref in refs.items()]
