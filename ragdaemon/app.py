from pathlib import Path

from flask import Flask, render_template

from ragdaemon.call_graph import get_call_graph


app = Flask(__name__)


# Initialize it
graph = get_call_graph(Path.cwd()) 
 

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
