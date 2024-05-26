import astroid

from ragdaemon.annotators.chunker.utils import Chunk, RawChunk, resolve_raw_chunks
from ragdaemon.errors import RagdaemonError


async def chunk_document(document: str) -> list[Chunk]:
    # Parse the code into an astroid AST
    lines = document.split("\n")
    file_path = lines[0].strip()
    code = "\n".join(lines[1:])

    tree = astroid.parse(code)

    chunks = list[RawChunk]()

    def extract_chunks(node, parent_path=None):
        if isinstance(node, (astroid.FunctionDef, astroid.ClassDef)):
            delimiter = ":" if parent_path == file_path else "."
            current_path = f"{parent_path}{delimiter}{node.name}"
            start_line, end_line = node.lineno, node.end_lineno
            if start_line is None or end_line is None:
                raise RagdaemonError(f"Function {node.name} has no line numbers.")
            chunks.append(
                RawChunk(id=current_path, start_line=start_line, end_line=end_line)
            )
            # Recursively handle nested functions
            for child in node.body:
                extract_chunks(child, parent_path=current_path)

    # Recursively extract chunks from the AST
    for node in tree.body:
        extract_chunks(node, parent_path=file_path)

    return resolve_raw_chunks(document, chunks)
