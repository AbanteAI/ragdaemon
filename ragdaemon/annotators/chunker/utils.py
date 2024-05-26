from typing import TypedDict

from ragdaemon.utils import lines_set_to_ref


class RawChunk(TypedDict):
    id: str
    start_line: int
    end_line: int


class Chunk(TypedDict):
    id: str
    ref: str


def resolve_chunk_parent(id: str, nodes: set[str]) -> str | None:
    file, chunk_str = id.split(":")
    if chunk_str == "BASE":
        return file
    elif "." not in chunk_str:
        return f"{file}:BASE"
    else:
        parts = chunk_str.split(".")
        while True:
            parent = f"{file}:{'.'.join(parts[:-1])}"
            if parent in nodes:
                return parent
            parent_str = parent.split(":")[1]
            if "." not in parent_str:
                return None
            # If intermediate parents are missing, skip them
            parts = parent_str.split(".")


def resolve_raw_chunks(document: str, chunks: list[RawChunk]) -> list[Chunk]:
    """Take a list of {id, start_line, end_line} and return a corrected list of {id, ref}."""

    # Convert to {id: set(lines)} for easier manipulation
    id_sets = {c["id"]: set(range(c["start_line"], c["end_line"] + 1)) for c in chunks}

    def update_parent_nodes(id: str, _id_sets: dict[str, set[int]]):
        parent_lines = _id_sets[id]
        child_chunks = {k: v for k, v in _id_sets.items() if k.startswith(id + ".")}
        if child_chunks:
            # Make sure end_line of each 'parent' chunk covers all children
            start_line = min(parent_lines)
            end_line = start_line
            for child_lines in child_chunks.values():
                if not child_lines:
                    continue
                end_line = max(end_line, max(child_lines))
            parent_lines = set(range(start_line, end_line + 1))
            # Remove child lines from parent lines
            for child_lines in child_chunks.values():
                parent_lines -= child_lines
            _id_sets[id] = parent_lines
        return _id_sets

    ids_longest_first = sorted(id_sets.keys(), key=lambda x: len(x), reverse=True)
    for id in ids_longest_first:
        id_sets = update_parent_nodes(id, id_sets)

    file_lines = document.split("\n")
    file = file_lines[0]
    output = list[Chunk]()
    if id_sets:
        # Generate a 'BASE chunk' with all lines not already part of a chunk
        base_chunk_lines = set(range(1, len(file_lines)))
        for lines in id_sets.values():
            base_chunk_lines -= lines
        lines_ref = lines_set_to_ref(base_chunk_lines)
        ref = f"{file}:{lines_ref}" if lines_ref else file
        base_chunk = Chunk(id=f"{file}:BASE", ref=ref)
        output.append(base_chunk)

    # Convert to refs and return
    for id, lines in id_sets.items():
        lines_ref = lines_set_to_ref(lines)
        ref = f"{file}:{lines_ref}" if lines_ref else file
        output.append(Chunk(id=id, ref=ref))
    return output
