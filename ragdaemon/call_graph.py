import ast
import subprocess
from pathlib import Path

import networkx as nx


def add_coordiantes_to_graph(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    # Add x, y coordiantes with spring layout
    pos = nx.spring_layout(G)
    for node in G.nodes:
        G.nodes[node]['x'] = pos[node][0]
        G.nodes[node]['z'] = pos[node][1]

    # Add z coordiante from PageRank. Reverse arrows temporarily
    G_reversed = G.reverse()
    pr = nx.pagerank(G_reversed)
    for node in G.nodes:
        G.nodes[node]['y'] = pr[node] * 10

    return G


def generate_ast_call_graph(paths: list[Path]) -> nx.MultiDiGraph:
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
                _from, _to = self.current, node.func.id
                if _from and _to:
                    self.graph.add_edge(_from, _to)
            self.generic_visit(node)

    G = nx.MultiDiGraph()
    for file_path in paths:
        with open(file_path, "r") as file:
            tree = ast.parse(file.read(), filename=file_path.name)
        visitor = CallGraphVisitor(G)
        visitor.visit(tree)
    
    return G

def generate_call_graph(directory: Path) -> nx.MultiDiGraph:
    
    # Get a list of paths in git project
    paths = subprocess.run(
        ["git", "ls-files"], cwd=directory, capture_output=True, text=True
    ).stdout.splitlines()
    paths = [Path(p) for p in paths if p.endswith(".py")]
    print(f"Found {len(paths)} python files in {directory}:")
    for path in paths:
        print(path)
    print()

    G = generate_ast_call_graph(paths)
    print(f"Generated graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges")

    G = add_coordiantes_to_graph(G)
    print("Added coordinates to graph")
    return G
