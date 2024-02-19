from pathlib import Path

import networkx as nx

from ragdaemon.treesitter.python_parser import parse_python_files
from ragdaemon.treesitter.setup import build_treesitter


def generate_treesitter_call_graph(G: nx.MultiDiGraph, paths: list[Path]) -> nx.MultiDiGraph:
    """Load paths into a call graph using treesitter."""
    if not (Path(__file__).parent / "ts-lang.so").exists():
        print(f"Building treesitter...")
        build_treesitter(cleanup=True)

    python_paths = [path for path in paths if path.suffix == ".py"]
    if python_paths:
        G = parse_python_files(G, python_paths)

    unsupported_extensions = {path.suffix for path in paths if path.suffix != ".py"}
    if unsupported_extensions:
        print(f"Unsupported file extensions: {unsupported_extensions}")
    
    return G
