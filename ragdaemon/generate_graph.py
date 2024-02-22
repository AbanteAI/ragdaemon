import json
from pathlib import Path
from typing import Any

from litellm import completion

from ragdaemon.utils import get_active_files, get_file_checksum


prompt = """\
You're parsing a CODEBASE into a GRAPH. 
You'll review one FILE, along with your WORKING GRAPH, and return a list of new NODES and EDGES as JSON data.

NODES represent functions, classes, and files.
NODE ATTRIBUTES:
- name: path, optionally followed by colon and dot-joined call stack, e.g. "app.py:home.render"
- type: "file" | "function" | "class" | "method"
- start_line: <int> | null
- end_line: <int> | null  # INCLUSIVE indexing
(- path: <str> will be inserted for you)

EDGES represent calls, encapsulation, or imports.
EDGE ATTRIBUTES:
- from: <node.name>
- to: <node.name>
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
        {"name": "app.py", "path": "app.py", "type": "file"},
        {"name": "README.md", "type": "file"},
        {"name": "requirements".txt", "type": "file"},
        {"name": "static/favicon.ico", "type": "file"},
        {"name": "static/js/main.js", "type": "file"},
        {"name": "templates/index.html", "type": "file"}
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
        {"name": "app.py:home", "start_line": 5, "end_line": 7, "type": "function"}
    ],
    "edges": [
        {"from": "requirements.txt", "to": "app.py", "type": "import"},
        {"from": "app.py", "to": "app.py:home", "type": "encapsulate"},
        {"from": "app.py:home", "to": "templates/index.html", "type": "call"}
    ]
}
--------------------------------------------------------------------------------"""


def get_pseudo_call_graph_for_file(
    file: Path, graph: dict[str, Any], cwd: Path, graph_cache: dict = {}
) -> dict[str, Any]:
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
        clean_graph = {
            "nodes": [
                {k: v for k, v in node.items() if k not in ("id", "path")} 
                for node in graph["nodes"]
            ],
            "edges": graph["edges"]
        }
        graph_message = json.dumps(clean_graph, indent=4)
        messages.insert(1, {"role": "user", "content": f"WORKING GRAPH:\n{graph_message}"})
        response = completion(
            model="gpt-4-turbo-preview",
            messages=messages,
            response_format={ "type": "json_object" },
        )
        new_graph = json.loads(response["choices"][0]["message"]["content"])
        # Add unique ID and path string for new nodes
        for node in new_graph["nodes"]:
            if node["type"] == "file":
                node["id"] = checksum
                node["path"] = f"{file}"
            else:
                node["id"] = f"{checksum}:{node['start_line']}:{node['end_line']}"
                node["path"] = f"{file}:{node['start_line']}-{node['end_line']}"
        graph_cache[checksum] = new_graph
    return graph_cache[checksum]


def generate_pseudo_call_graph(cwd: Path) -> dict[str, Any]:
    """Return a call graph of the whole codebase"""
    graph = {"nodes": [], "edges": []}
    text_files = get_active_files(cwd)
    
    # Build the active graph
    graph_cache = {}  # {file_checksum: {nodes: [], edges: []}}
    graph_cache_path = cwd / ".ragdaemon" / "graph_cache.json"
    if graph_cache_path.exists():
        with open(graph_cache_path, "r") as f:
            graph_cache = json.load(f)
    # TODO: Parallelize this
    for file in text_files:
        new_graph = get_pseudo_call_graph_for_file(Path(file), graph, cwd, graph_cache)
        graph["nodes"].extend(new_graph["nodes"])
        graph["edges"].extend(new_graph["edges"])
    with open(graph_cache_path, "w") as f:
        f.write(json.dumps(graph_cache, indent=4))

    # Ignore conflicts (edges to incorrectly-guessed nodes)
    # TODO: Better error correction: resolve conflicts, require <=1 edge per node
    all_nodes = {node["name"] for node in graph["nodes"]}
    graph["edges"] = [
        edge for edge in graph["edges"] 
        if edge["to"] in all_nodes and edge["from"] in all_nodes
    ]
    return graph


if __name__ == "__main__":
    path = Path.home() / "flask-three"
    graph_path = path / ".ragdaemon" / "graph.json"
    graph_path.parent.mkdir(exist_ok=True)
    graph = generate_pseudo_call_graph(path)
    with open(graph_path, "w") as f:
        f.write(json.dumps(graph, indent=4))
    