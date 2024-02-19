from pathlib import Path

import networkx as nx
from tree_sitter import Language, Node, Parser

from ragdaemon.treesitter.build_treesitter import build_treesitter


def _clean_text(node: Node) -> str:
    """Return a cleaned version of the node's text."""
    return " ".join(node.text.decode("utf-8").split())


def _clean_field(node: Node, field: str) -> str:
    """Return the text of a specified field from a node."""
    _field = node.child_by_field_name(field)
    return _clean_text(_field) if _field else ""


def parse_node(G: nx.MultiDiGraph, node: Node, path_str: str, namespace: dict) -> nx.MultiDiGraph:
    """Add relevant parts of a node (recursively) to the graph and namespace."""
    node_type = node.type

    # Imports: Load into namespace
    if node_type in ("import_statement", "import_from_statement"):
        import_text = _clean_text(node)
        _module, _target = import_text.split("import")
        if _module:
            _module = _module.replace("from", "").strip()
        else:
            _module = ""
        for target in _target.split(","):
            target = target.strip()
            alias = target
            if " as " in alias:
                target, alias = alias.split(" as ")
            if _module:
                target = _module + ":" + target
            namespace[alias] = target
            
    # Classes: Add nodes, pass path_str:<class_name> to children
    elif node_type == "class_definition":
        class_name = _clean_field(node, "name")
        node_name = f"{path_str}:{class_name}"
        G.add_node(node_name, type="class")
        namespace[class_name] = node_name
        for child in node.children:
            G = parse_node(G, child, node_name, namespace)

    # Functions: Add nodes, pass path_str.<function_name> to children
    elif node_type == "function_definition":
        function_name = _clean_field(node, "name")
        node_name = f"{path_str}:{function_name}"
        G.add_node(node_name, type="function")
        namespace[function_name] = node_name
        for child in node.children:
            G = parse_node(G, child, node_name, namespace.copy())

    # Calls: Add edges, use path_str and the function name
    elif node_type == "call":
        from_node = path_str
        to_node = _clean_field(node, "function")
        if "." in to_node: # methods
            splits = to_node.split(".")
            to_node = splits[-1]
            caller = ".".join(splits[:-1])
            if caller in namespace:
                to_node = f"{namespace[caller]}:{to_node}"
            else:
                # TODO: Match based on variable type (namespace)
                pass
        if to_node in namespace:
            to_node = namespace[to_node]
        else:
            # TODO: Label built-in functions
            pass
        G.add_edge(from_node, to_node)
        for child in node.children:
            G = parse_node(G, child, path_str, namespace)

    elif node.children:
        for child in node.children:
            G = parse_node(G, child, path_str, namespace)    
    
    return G


def parse_python_file(parser: Parser, path: Path) -> nx.MultiDiGraph:
    """Return a new call graph from a Python file."""
    G = nx.MultiDiGraph()

    path_str = ".".join(path.with_suffix("").parts)
    namespace = {}  # {alias: target}

    source_code = path.read_text()
    tree = parser.parse(bytes(source_code, "utf8"))
    cursor = tree.walk()
    cursor.goto_first_child()
    while True:
        G = parse_node(G, cursor.node, path_str, namespace)
        if not cursor.goto_next_sibling():
            break

    # Resolve namespace
    for node in G.nodes:
        if node in namespace:
            G.add_node(namespace[node], **G.nodes[node])
            for _from, _, data in G.in_edges(node, data=True):
                G.add_edge(_from, namespace[node], **data)
            for _, _to, data in G.out_edges(node, data=True):
                G.add_edge(namespace[node], _to, **data)
            G.remove_node(node)
    return G


def parse_python_files(G: nx.MultiDiGraph, paths: list[Path]) -> nx.MultiDiGraph:
    """Load Python files into a call graph."""
    # Initialize Python parser
    parser = Parser()
    language = Language(Path(__file__).parent / "ts-lang.so", "python")
    parser.set_language(language)

    # Generate graphs for each file independently
    subgraphs = []
    for path in paths:
        _G = parse_python_file(parser, path)
        subgraphs.append(_G)

    # Merge. TODO: Resolve node names with importlib.util
    for graph in subgraphs:
        G = nx.compose(G, graph)

    return G


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
