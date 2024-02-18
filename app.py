import ast
from pathlib import Path
import json

import networkx as nx
from flask import Flask, render_template

app = Flask(__name__)

def generate_call_graph(directory: Path) -> nx.MultiDiGraph:
    class CallGraphVisitor(ast.NodeVisitor):
        def __init__(self, graph):
            self.graph = graph
            self.current = None

        def visit_FunctionDef(self, node):
            self.current = node.name
            self.generic_visit(node)
            self.current = None

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name):
                self.graph.add_edge(self.current, node.func.id)
            self.generic_visit(node)

    G = nx.MultiDiGraph()
    for file_path in directory.rglob('*.py'):
        with open(file_path, "r") as file:
            tree = ast.parse(file.read(), filename=file_path.name)
        visitor = CallGraphVisitor(G)
        visitor.visit(tree)
    return G

@app.route('/')
def home():
    # Generate the call graph
    codebase = Path("multifile_calculator")
    graph = generate_call_graph(codebase)

    # Serialize and send to frontend
    nodes = [{'id': node} for node in graph.nodes]
    links = [{'source': source, 'target': target} for source, target in graph.edges]
    metadata = {
        'num_nodes': len(nodes),
        'num_edges': len(links)
    }
    return render_template('index.html', nodes=nodes, links=links, metadata=metadata)

if __name__ == '__main__':
    app.run(debug=True)
