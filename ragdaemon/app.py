from pathlib import Path

from flask import Flask, render_template

from ragdaemon.generate_graph import generate_pseudo_call_graph
from ragdaemon.position_nodes import add_coordiantes_to_graph


app = Flask(__name__)


# Initialize it
graph = generate_pseudo_call_graph(Path.cwd()) 
graph = add_coordiantes_to_graph(graph)

@app.route('/')
def home():
    global graph

    # Serialize and send to frontend
    nodes = [{'id': node, **data} for node, data in graph.nodes(data=True)]
    edges = [{'source': source, 'target': target, **data} for source, target, data in graph.edges(data=True)]
    metadata = {
        'num_nodes': len(nodes),
        'num_edges': len(edges)
    }
    return render_template('index.html', nodes=nodes, edges=edges, metadata=metadata)


def main():
    app.run(host="localhost", port=5001, debug=True)
