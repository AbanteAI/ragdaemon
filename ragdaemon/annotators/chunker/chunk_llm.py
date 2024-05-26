import json
from collections import Counter, defaultdict
from functools import partial
from json.decoder import JSONDecodeError
from typing import List, Optional

from spice import Spice, SpiceMessages
from spice.models import GPT_4o

from ragdaemon.annotators.chunker.utils import (
    Chunk,
    RawChunk,
    resolve_chunk_parent,
    resolve_raw_chunks,
)
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import semaphore


class ChunkErrorInPreviousBatch(RagdaemonError):
    pass


def validate(
    response: str,
    file: str,
    max_line: int,
    file_chunks: Optional[set[str]],
    last_chunk: Optional[RawChunk],
):
    try:
        chunks = json.loads(response).get("chunks")
    except JSONDecodeError:
        return False
    if not isinstance(chunks, list):
        return False
    if not all(isinstance(chunk, dict) for chunk in chunks):
        return False

    for chunk in chunks:
        if not set(chunk.keys()) == {"id", "start_line", "end_line"}:
            return False

        halves = chunk["id"].split(":")
        if len(halves) != 2 or not halves[0] or not halves[1]:
            return False
        if halves[0] != file:
            return False

        start, end = chunk.get("start_line"), chunk.get("end_line")
        if start is None or end is None:
            return False

        # Sometimes output is int, sometimes string. This accomodates either.
        start, end = str(start), str(end)
        if not start.isdigit() or not end.isdigit():
            return False
        start, end = int(start), int(end)

        if not 1 <= start <= end <= max_line:
            return False

    if last_chunk is not None:
        if not any(chunk["id"] == last_chunk["id"] for chunk in chunks):
            return False

    """
    The LLM sometimes returns invalid parents (i.e. path/to/file.ext:parent.chunk).
    There are 3 cases why they might be invalid:
    A) The LLM made a typo here. In that case, return False to try again.
    B) The LLM made a typo when parsing the parent in a previous batch. In that case,
       go back and redo the previous batch. We distinguish this from case A) by checking
       if multiple chunks reference the same invalid parent.
    C) An edge case where our schema breaks down, e.g. Javascript event handlers 
       usually try to set "document" as their parent, but that won't be a node.
    
    Case A) should be resolved by Spice's validator loop, i.e. this function returning 
    "False". For Case B), raise a special exception and step back one batch in the 
    chunk_document loop. Any chunks still referencing invalid parents after these two 
    loops are exhausted (including case C)) will just be accepted and linked to 
    path/to/file.ext:BASE.
    """
    if file_chunks:  # else, loops exhausted or Case C)
        valid_parents = file_chunks.copy()
        chunks_shortest_first = sorted(chunks, key=lambda x: len(x["id"]))
        chunks_missing_parents = set()
        for chunk in chunks_shortest_first:
            if not resolve_chunk_parent(chunk["id"], valid_parents):
                chunks_missing_parents.add(chunk["id"])
            valid_parents.add(chunk["id"])

        if len(chunks_missing_parents) > 1:
            missing_parents = []
            for chunk in chunks_missing_parents:
                file, chunk_str = chunk.split(":")
                parts = chunk_str.split(".")
                missing_parents.append(f"{file}:{'.'.join(parts[:-1])}")
            mp_counts = Counter(missing_parents)
            parent, count = mp_counts.most_common(1)[0]
            if count > 1:
                raise ChunkErrorInPreviousBatch(parent)  # Case B)
            return False  # Case A)

    return True


async def get_llm_response(
    spice_client: Spice,
    file: str,
    file_lines: list[str],
    file_chunks: Optional[set[str]] = None,
    last_chunk: Optional[RawChunk] = None,
    verbose: int = 0,
) -> List[RawChunk]:
    """Get one chunking response from the LLM model."""
    messages = SpiceMessages(spice_client)
    messages.add_system_prompt(name="chunk_llm.base")
    if last_chunk is not None:
        messages.add_system_prompt("chunk_llm.continuation", last_chunk=last_chunk)
    messages.add_user_prompt("chunk_llm.user", path=file, code="\n".join(file_lines))

    max_line = int(file_lines[-1].split(":")[0])  # Extract line number
    validator = partial(
        validate,
        file=file,
        max_line=max_line,
        file_chunks=file_chunks,
        last_chunk=last_chunk,
    )
    async with semaphore:
        try:
            response = await spice_client.get_response(
                messages=messages,
                model=GPT_4o,
                response_format={"type": "json_object"},
                validator=validator,
                retries=2,
            )
            return json.loads(response.text).get("chunks")
        except ValueError:
            pass
        validator = partial(
            validate,
            file=file,
            max_line=max_line,
            file_chunks=None,  # Skip parent chunk validation
            last_chunk=last_chunk,
        )
        try:
            response = await spice_client.get_response(
                messages=messages,
                model=GPT_4o,
                response_format={"type": "json_object"},
                validator=validator,
                retries=1,
            )
            return json.loads(response.text).get("chunks")
        except ValueError:
            if verbose > 0:
                print(
                    f"Failed to get chunks for {file} batch ending at line {max_line}."
                )
            return []


async def chunk_document(
    document: str,
    spice_client: Spice,
    retries=1,
    batch_size: int = 800,
    verbose: int = 0,
) -> list[Chunk]:
    """Parse file_lines into a list of {id, ref} chunks."""
    lines = document.split("\n")
    file = lines[0]
    file_lines = lines[1:]
    if not file_lines or not any(line for line in file_lines):
        return []
    file_lines = [f"{i+1}:{line}" for i, line in enumerate(file_lines)]

    # Get raw llm output: {id, start_line, end_line}
    chunks = list[RawChunk]()
    n_batches = (len(file_lines) + batch_size - 1) // batch_size
    retries_by_batch = {i: retries for i in range(n_batches)}
    chunk_index_by_batch = defaultdict(int)
    i = 0
    while i < n_batches:
        while retries_by_batch[i] >= 0:
            batch_lines = file_lines[i * batch_size : (i + 1) * batch_size]
            chunk_index_by_batch[i] = len(chunks)
            last_chunk = chunks.pop() if chunks else None
            if retries_by_batch[i] > 0:
                file_chunks = {c["id"] for c in chunks}
            else:
                file_chunks = None  # Skip parent chunk validation
            try:
                _chunks = await get_llm_response(
                    spice_client,
                    file,
                    batch_lines,
                    file_chunks,
                    last_chunk,
                )
                chunks.extend(_chunks)
                i += 1
                break
            except ChunkErrorInPreviousBatch as e:
                if verbose > 1:
                    print(f"Chunker missed parent {e} in file {file}, retrying.")
                retries_by_batch[i] -= 1
                chunks = chunks[: chunk_index_by_batch[i]]
                i = max(0, i - 1)

    return resolve_raw_chunks(document, chunks)
