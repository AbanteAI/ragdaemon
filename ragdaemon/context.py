from pathlib import Path
from typing import Any

import networkx as nx

from ragdaemon.annotators.diff import parse_diff_id
from ragdaemon.database import get_db
from ragdaemon.utils import parse_path_ref


class ContextBuilder:
    """Renders items from a graph into an llm-readable string."""

    def __init__(self, graph: nx.MultiDiGraph, verbose: bool = False):
        self.graph = graph
        self.verbose = verbose
        self.context = dict[
            str, dict[str, Any]
        ]()  # {path: {lines, tags, document, diff}}

    def _add_path(self, path_str: str):
        """Create a new record in the context for the given path."""
        cwd = self.graph.graph["cwd"]
        if path_str not in self.graph:  # e.g. deleted file
            document = ""
        else:
            checksum = self.graph.nodes[path_str]["checksum"]
            document = get_db(cwd).get(checksum)["documents"][0]
        message = {
            "lines": set(),
            "tags": set(),
            "document": document,
            "diffs": set(),
        }
        self.context[path_str] = message

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

    def render(self) -> str:
        """Return a formatted context message for the given nodes."""
        output = ""
        for path_str, data in self.context.items():
            if output:
                output += "\n"
            tags = "" if not data["tags"] else f" ({', '.join(sorted(data['tags']))})"
            output += f"{path_str}{tags}\n"
            if data["lines"]:
                file_lines = data["document"].splitlines()
                last_rendered = 0
                for line in sorted(data["lines"]):
                    if line - last_rendered > 1:
                        output += "...\n"
                    output += f"{line}:{file_lines[line]}\n"
                    last_rendered = line
                if last_rendered < len(file_lines) - 1:
                    output += "...\n"
            if data["diffs"]:
                output += self.render_diffs(data["diffs"])
        return output

    def render_diffs(self, ids: set[str]) -> str:
        output = ""
        diff_str, _, _ = parse_diff_id(next(iter(ids)))
        git_command = "--git diff"
        if diff_str != "DEFAULT":
            git_command += f" {diff_str}"
        output += f"{git_command}\n"
        cwd = self.graph.graph["cwd"]
        for id in sorted(ids):
            checksum = self.graph.nodes[id]["checksum"]
            document = get_db(cwd).get(checksum)["documents"][0]
            # TODO: Add line numbers
            without_git_command = "\n".join(document.splitlines()[1:])
            output += without_git_command + "\n"
        return output

    def to_refs(self) -> list[str]:
        """Return a list of path:interval,interval for everything in current context."""
        refs = dict[Path, str]()
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
