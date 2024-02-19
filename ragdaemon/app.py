from pathlib import Path

from flask import Flask, render_template

from ragdaemon.call_graph import generate_call_graph


app = Flask(__name__)


@app.route('/')
def home():
    # Generate the call graph
    codebase = Path.cwd()
    graph = generate_call_graph(codebase)

    # Serialize and send to frontend
    nodes = [{'id': node, **data} for node, data in graph.nodes(data=True)]
    links = [{'source': source, 'target': target, **data} for source, target, data in graph.edges(data=True)]
    metadata = {
        'num_nodes': len(nodes),
        'num_edges': len(links)
    }
    return render_template('index.html', nodes=nodes, links=links, metadata=metadata)


def main():
    app.run(host="localhost", port=5001, debug=True)
