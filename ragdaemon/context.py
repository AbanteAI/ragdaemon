import networkx as nx

from ragdaemon.database import get_db
from ragdaemon.utils import parse_ref


class ContextBuilder:
    """Renders items from a graph into an llm-readable string."""
    def __init__(self, graph: nx.MultiDiGraph, verbose: bool = False):
        self.graph = graph
        self.verbose = verbose
        self.context = {}  # {path: {lines, tags, document}}

    def add(self, ref: str, tags: list[str] = []):
        """Take an ref and add to context"""
        path_str, lines_ref = parse_ref(ref)
        if path_str not in self.graph:
            if self.verbose:
                print(f"Warning: no matching message found for {ref}.")
            return
        if path_str not in self.context:
            cwd = self.graph.graph["cwd"]
            checksum = self.graph.nodes[path_str]["checksum"]
            message = {
                "lines": set(),
                "tags": set(),
                "document": get_db(cwd).get(checksum)["documents"][0],
            }
            self.context[path_str] = message
        self.context[path_str]["tags"].update(tags)
        if lines_ref:
            for _range in lines_ref.split(","):
                if "-" in _range:
                    start, end = _range.split("-")
                    for i in range(int(start), int(end) + 1):
                        self.context[path_str]["lines"].add(i)
                else:
                    self.context[path_str]["lines"].add(int(_range))
        else:
            for i in range(1, len(self.context[path_str]["document"].splitlines())):
                self.context[path_str]["lines"].add(i)  # +1 line for filename, -1 for indexing

    def remove(self, ref: str):
        """Remove the given ref from the context."""
        path_str, lines_ref = parse_ref(ref)
        if path_str not in self.context:
            if self.verbose:
                print(f"Warning: no matching message found for {path_str}.")
            return        
        if lines_ref is None:
            del self.context[path_str]
            return
        ranges = lines_ref.split(",")
        lines = set()
        for ref in ranges:
            if "-" in ref:
                start, end = ref.split("-")
                lines.update(range(int(start), int(end) + 1))
            else:
                lines.add(int(ref))
        self.context[path_str]["lines"] -= lines
        if not self.context[path_str]["lines"]:
            del self.context[path_str]

    def render(self) -> str:
        """Return a formatted context message for the given nodes."""
        output = ""
        for path_str, data in self.context.items():
            if output:
                output += "\n"
            tags = "" if "tags" not in data else f" ({', '.join(data['tags'])})"
            output += f"{path_str}{tags}\n"

            file_lines = data["document"].splitlines()
            last_rendered = 0
            for line in sorted(data["lines"]):
                if line - last_rendered > 1:
                    output += "...\n"
                output += f"{line}:{file_lines[line]}\n"
                last_rendered = line
            if last_rendered < len(file_lines) - 1:
                output += "...\n"
        return output
