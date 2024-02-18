from pathlib import Path

import networkx as nx
from flask import Flask, render_template

app = Flask(__name__)

def generate_call_graph(path: Path) -> nx.MultiDiGraph:
    pass

@app.route('/')
def home():
    graph = generate_call_graph(Path('test.py'))
    print(graph)
    # Generate a call graph
    # Generate coordinates
    # Graph them
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
