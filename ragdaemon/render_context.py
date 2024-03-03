import networkx as nx

from ragdaemon.database import get_db


def render_context_message(context: dict[str, dict]) -> str:
    """Return a formatted context message for the given nodes."""
    output = ""
    for data in context.values():
        if output:
            output += "\n"
        tags = "" if "tags" not in data else f" ({', '.join(data['tags'])})"
        output += f"{data['id']}{tags}\n"

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


def add_id_to_context(
    graph: nx.MultiDiGraph,
    id: str,
    context: dict,
    tags: list[str],
    verbose: bool = False,
):
    """Take an id like path/to/file.suffix:line_start-line_end and add to context"""
    path, lines_ref = id, None
    if ":" in id:
        path, lines_ref = id.split(":", 1)
    if path not in graph:
        if verbose:
            print(f"Warning: no matching message found for {id}.")
        return
    if path not in context:
        cwd = graph.graph["cwd"]
        checksum = graph.nodes[path]["checksum"]
        message = {
            "id": id,
            "lines": set(),
            "tags": set(),
            "document": get_db(cwd).get(checksum)["documents"][0],
        }
        context[path] = message
    else:
        context[path]["id"] = context[path]["id"].split(":")[0]
    context[path]["tags"].update(tags)
    if lines_ref:
        for _range in lines_ref.split(","):
            if "-" in _range:
                start, end = _range.split("-")
                for i in range(int(start), int(end) + 1):
                    context[path]["lines"].add(i)
            else:
                context[path]["lines"].add(int(_range))
    else:
        for i in range(1, len(context[path]["document"].splitlines())):
            context[path]["lines"].add(i)  # +1 line for filename, -1 for indexing
    return context
