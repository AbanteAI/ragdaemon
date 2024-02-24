from pathlib import Path

import networkx as nx

from ragdaemon.annotators.base_annotator import Annotator


class LayoutCallgraph(Annotator):
    name = "layout_callgraph"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        # If all nodes have "layout.callgraph"
        pass

    def annotate(self, graph: nx.MultiDiGraph, cwd: Path) -> nx.MultiDiGraph:
        """
        a. Regenerate x/y/z for all nodes
        b. Update all nodes
        c. Save to chroma
        """
        pass



# FROM ragdaemon/generate_graph.py (old)
import asyncio
import json
from pathlib import Path

from litellm import acompletion
import networkx as nx
from tqdm.asyncio import tqdm

from ragdaemon.utils import get_active_files, get_file_checksum
from ragdaemon.database import get_db, save_db


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

async def get_pseudo_call_graph_for_file(
    file: Path, graph: RDGraph, cwd: Path
) -> RDGraph:
    file_lines = (cwd / file).read_text().splitlines()
    numbered_lines = "\n".join(f"{i+1}:{line}" for i, line in enumerate(file_lines))
    file_message = (f"{file}\n{numbered_lines}")
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"FILE:\n{file_message}"},
    ]
    checksum = get_file_checksum(cwd / file)
    if not get_db().exists(checksum):
        # TODO: Add retry loop
        graph_message = graph._render_graph_message()
        messages.insert(1, {"role": "user", "content": f"WORKING GRAPH:\n{graph_message}"})
        response = await acompletion(
            model="gpt-4-turbo-preview",
            messages=messages,
            response_format={ "type": "json_object" },
        )
        new_nodes_and_edges = json.loads(response["choices"][0]["message"]["content"])
        # Add unique ID and path string for new nodes
        for node in new_nodes_and_edges["nodes"]:
            _start, _end = node.get("start_line"), node.get("end_line")
            if not _start or not _end:
                continue  # TODO: Handle
            node["path"] = f"{file}:{_start}-{_end}"
            node["checksum"] = f"{checksum}:{_start}-{_end}"
        # Add a node for the file itself
        new_nodes_and_edges["nodes"].append({
            "id": f"{file}", 
            "type": "file", 
            "start_line": None,
            "end_line": None,
            "path": f"{file}",
            "checksum": checksum
        })
        # TODO: Do encapsulate nodes manually
        get_db().set(checksum, new_nodes_and_edges)
    return get_db().get(checksum)


async def generate_pseudo_call_graph(cwd: Path) -> RDGraph:
    """Return a call graph of the whole codebase"""
    graph = RDGraph()
    text_files = get_active_files(cwd)
    
    # Add all text files' names to the graph for context
    for file in text_files:
        graph.add_node(
            node_for_adding=f"{file}",
            type="file"
        )
    
    # Parse all files with LLM
    semaphore = asyncio.Semaphore(20)
    async def _get_pseudo_call_graph_for_file(file: Path):
        async with semaphore:
            new_graph = await get_pseudo_call_graph_for_file(Path(file), graph, cwd)
            for node in new_graph["nodes"]:
                if not all(k in node for k in ("id", "type", "path", "checksum")):
                    continue 
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
    tasks = [_get_pseudo_call_graph_for_file(file) for file in text_files]
    await tqdm.gather(*tasks, desc="Generating File Graph", unit="file")

    save_db()

    # TODO: Conflict resolution, require at least one valid edge per node
    _edges = list(graph.edges)
    for edge in _edges:
        missing = next((node for node in edge if node not in graph.nodes), None)
        if missing:  # Incorrect guesses
            graph.remove_edge(*edge)
            if missing in graph.nodes:
                graph.remove_node(missing)
    return graph

