import json
from pathlib import Path
from typing import Any

from litellm import completion
import networkx as nx

from ragdaemon.utils import get_active_files, get_file_checksum


prompt = """\
You're parsing a CODEBASE into a GRAPH. 
You'll review one FILE, along with your WORKING GRAPH, and return a list of new NODES and EDGES as JSON data.

NODES represent functions, classes, and files.
NODE ATTRIBUTES:
- id: path, optionally followed by colon and dot-joined call stack, e.g. "app.py:home.render"
- type: "file" | "function" | "class" | "method"
- start_line: <int> | null
- end_line: <int> | null  # INCLUSIVE indexing

EDGES represent calls, encapsulation, or imports.
EDGE ATTRIBUTES:
- source: <node.id>
- target: <node.id>
- type: "import" | "encapsulates" | "call"

Procedure for parsing FILE:
1. Look over the imports. If the FILE imports any third-party libraries (e.g. numpy, react), CREATE one EDGE of type "import" from the FILE to the file where the package is specified (e.g. "requirements.txt", "package.json").
2. Identify functions, classes and methods. CREATE one NODE for each of its respective type.
3. CREATE one EDGE of type "encapsulate" from each node created in (2.) to its encapsulating node.
4. Identify calls to other nodes in this codebase. These could be explicit (calling an local or imported function) or implicit (passing a reference to a file to an library function).
5. CREATE one EDGE of type "call" for each call identified in (4.). If the target node does not exist, do your best to infer its name.
6. Return a list of new NODES and EDGES as JSON data.

EXAMPLE:
--------------------------------------------------------------------------------
WORKING GRAPH:
{
    "nodes": [
        {"id": "app.py", "path": "app.py", "type": "file"},
        {"id": "README.md", "type": "file"},
        {"id": "requirements".txt", "type": "file"},
        {"id": "static/favicon.ico", "type": "file"},
        {"id": "static/js/main.js", "type": "file"},
        {"id": "templates/index.html", "type": "file"}
    ],
    "edges": []
}

FILE:
app.py
1:from flask import Flask, render_template
2:
3:app = Flask(__name__)
4:
5:@app.route('/')
6:def home():
7:    return render_template('index.html')
8:
9:if __name__ == '__main__':
10:    app.run(host="localhost", port="5001", debug=True)
11:

RESPONSE:
{
    "nodes": [
        {"id": "app.py:home", "start_line": 5, "end_line": 7, "type": "function"}
    ],
    "edges": [
        {"source": "requirements.txt", "target": "app.py", "type": "import"},
        {"source": "app.py", "target": "app.py:home", "type": "encapsulate"},
        {"source": "app.py:home", "target": "templates/index.html", "type": "call"}
    ]
}
--------------------------------------------------------------------------------"""


class RDGraph(nx.MultiDiGraph):
    def _render_graph_message(self) -> str:
        """Convert the graph to a JSON string with only llm-friendly attributes."""
        node_fields = ("start_line", "end_line", "type")
        return json.dumps({
            "nodes": [
                {'id': node, **{k: v for k, v in data.items() if k in node_fields}}
                for node, data in self.nodes(data=True)
            ],
            "edges": [
                {'source': source, 'target': target, **data} 
                for source, target, data in self.edges(data=True)
            ]
        }, indent=4)


def get_pseudo_call_graph_for_file(
    file: Path, graph: RDGraph, cwd: Path, graph_cache: dict = {}
) -> RDGraph:
    file_lines = (cwd / file).read_text().splitlines()
    numbered_lines = "\n".join(f"{i+1}:{line}" for i, line in enumerate(file_lines))
    file_message = (f"{file}\n{numbered_lines}")
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"FILE:\n{file_message}"},
    ]
    checksum = get_file_checksum(cwd / file)
    # TODO: Also check some graph dependencies, e.g. parents' checksums
    if checksum not in graph_cache:
        graph_message = graph._render_graph_message()
        messages.insert(1, {"role": "user", "content": f"WORKING GRAPH:\n{graph_message}"})
        response = completion(
            model="gpt-4-turbo-preview",
            messages=messages,
            response_format={ "type": "json_object" },
        )
        new_nodes_and_edges = json.loads(response["choices"][0]["message"]["content"])
        # Add unique ID and path string for new nodes
        for node in new_nodes_and_edges["nodes"]:
            line_id = f":{node['start_line']}-{node['end_line']}"
            node["path"] = f"{file}:{line_id}"
            node["checksum"] = f"{checksum}:{line_id}"
        # Add a node for the file itself
        new_nodes_and_edges["nodes"].append({
            "id": f"{file}", 
            "type": "file", 
            "start_line": None,
            "end_line": None,
            "path": f"{file}",
            "checksum": checksum
        })
        graph_cache[checksum] = new_nodes_and_edges
    return graph_cache[checksum]


def generate_pseudo_call_graph(cwd: Path) -> RDGraph:
    """Return a call graph of the whole codebase"""
    graph = RDGraph()
    text_files = get_active_files(cwd)
    
    # Build the active graph
    graph_cache = {}  # {file_checksum: {nodes: [], edges: []}}
    graph_cache_path = cwd / ".ragdaemon" / "graph_cache.json"
    if graph_cache_path.exists():
        with open(graph_cache_path, "r") as f:
            graph_cache = json.load(f)
    # Add all text files' names to the graph for context
    for file in text_files:
        graph.add_node(
            node_for_adding=f"{file}",
            type="file"
        )
    # TODO: Parallelize this
    for file in text_files:
        new_graph = get_pseudo_call_graph_for_file(Path(file), graph, cwd, graph_cache)
        for node in new_graph["nodes"]:
            graph.add_node(
                node_for_adding=node["id"],
                type=node["type"],
                start_line=node.get("start_line"),
                end_line=node.get("end_line"),
                path=node["path"],
                checksum=node["checksum"],
            )
        for edge in new_graph["edges"]:
            graph.add_edge(
                u_for_edge=edge["source"],
                v_for_edge=edge["target"],
                key=None,
                type=edge["type"],
            )
    with open(graph_cache_path, "w") as f:
        f.write(json.dumps(graph_cache, indent=4))

    # TODO: Conflict resolution, require at least one valid edge per node
    for edge in graph.edges:
        missing = next((node for node in edge if node not in graph.nodes), None)
        if missing:  # Incorrect guesses
            graph.remove_edge(*edge)
            graph.remove_node(missing)
    return graph


if __name__ == "__main__":
    path = Path.home() / "flask-three"
    graph_path = path / ".ragdaemon" / "graph.json"
    graph_path.parent.mkdir(exist_ok=True)
    graph = generate_pseudo_call_graph(path)
    # Save the graph using networkx's JSON format
    data = nx.readwrite.json_graph.node_link_data(graph)
    with open(graph_path, "w") as f:
        json.dump(data, f, indent=4)
