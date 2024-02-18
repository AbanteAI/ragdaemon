import ast
from pathlib import Path

import networkx as nx

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

    # Add x, y coordiantes with spring layout
    pos = nx.spring_layout(G)
    for node in G.nodes:
        G.nodes[node]['x'] = pos[node][0]
        G.nodes[node]['z'] = pos[node][1]
    # Add z coordiante from PageRank. Reverse arrows temporarily
    G_reversed = G.reverse()
    pr = nx.pagerank(G_reversed)
    for node in G.nodes:
        G.nodes[node]['y'] = pr[node]

    return G
