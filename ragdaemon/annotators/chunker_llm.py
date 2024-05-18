import json
from functools import partial
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional

from spice import SpiceMessages
from spice.models import TextModel

from ragdaemon.annotators.chunker import Chunker, resolve_chunk_parent
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import DEFAULT_COMPLETION_MODEL, lines_set_to_ref, semaphore


def validate(
    response: str,
    file: str,
    max_line: int,
    file_chunks: set[str] | None,
    last_chunk: Optional[dict[str, Any]],
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
            return False  # Chunk is missing fields

        halves = chunk["id"].split(":")
        if len(halves) != 2 or not halves[0] or not halves[1]:
            return False  # Chunk ID is not in the correct format
        if halves[0] != file:
            return False

        start, end = chunk.get("start_line"), chunk.get("end_line")
        if start is None or end is None:
            return False  # Chunk lines are missing

        # Sometimes output is int, sometimes string. This accomodates either.
        start, end = str(start), str(end)
        if not start.isdigit() or not end.isdigit():
            return False  # Chunk lines are not valid
        start, end = int(start), int(end)

        if not 1 <= start <= end <= max_line:
            return False  # Chunk lines are out of bounds
        # TODO: Validate the ref, i.e. a parent chunk exists

    if last_chunk is not None:
        if not any(chunk["id"] == last_chunk["id"] for chunk in chunks):
            return False

    if file_chunks is not None:
        valid_parents = file_chunks.copy()
        chunks_shortest_first = sorted(chunks, key=lambda x: len(x["id"]))
        for chunk in chunks_shortest_first:
            if not resolve_chunk_parent(chunk["id"], valid_parents):
                return False
            valid_parents.add(chunk["id"])

    return True


class ChunkerLLM(Chunker):
    name = "chunker_llm"
    chunk_field_id = "chunks_llm"

    def __init__(
        self,
        *args,
        batch_size: int = 800,
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.batch_size = batch_size
        self.model = model

    async def get_llm_response(
        self,
        file: str,
        file_lines: list[str],
        file_chunks: set[str],
        last_chunk: Optional[dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Get one chunking response from the LLM model."""
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")

        messages = SpiceMessages(self.spice_client)
        messages.add_system_prompt(name="chunker_llm.base")
        if last_chunk is not None:
            messages.add_system_prompt(
                "chunker_llm.continuation", last_chunk=last_chunk
            )
        messages.add_user_prompt(
            "chunker_llm.user", path=file, code="\n".join(file_lines)
        )

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
                response = await self.spice_client.get_response(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                    validator=validator,
                    retries=2,
                )
                return json.loads(response.text).get("chunks")
            except ValueError:
                pass
            # It's possible the parent chunk just doens't exist. So try once more and
            # disregard that - it will just be linked to the BASE chunk instead.
            validator = partial(
                validate,
                file=file,
                max_line=max_line,
                file_chunks=None,
                last_chunk=last_chunk,
            )
            try:
                response = await self.spice_client.get_response(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                    validator=validator,
                    retries=1,
                )
                return json.loads(response.text).get("chunks")
            except ValueError:
                if self.verbose:
                    print(
                        f"Failed to get response for {file} batch ending at line {max_line}."
                    )
                return []

    async def chunk_document(self, document: str) -> list[dict[str, Any]]:
        """Parse file_lines into a list of {id, ref} chunks."""
        lines = document.split("\n")
        file = lines[0]
        file_lines = lines[1:]
        if not file_lines or not any(line for line in file_lines):
            return []
        file_lines = [f"{i+1}:{line}" for i, line in enumerate(file_lines)]

        # Get raw llm output: {id, start_line, end_line}
        chunks = list[dict[str, Any]]()
        n_batches = (len(file_lines) + self.batch_size - 1) // self.batch_size
        for i in range(n_batches):
            batch_lines = file_lines[i * self.batch_size : (i + 1) * self.batch_size]
            file_chunks = set(chunk["id"] for chunk in chunks)
            last_chunk = chunks.pop() if chunks else None
            _chunks = await self.get_llm_response(
                file, batch_lines, file_chunks, last_chunk
            )
            chunks.extend(_chunks)

        # Convert to {id: set(lines)} for easier manipulation
        chunks = {
            c["id"]: set(range(c["start_line"], c["end_line"] + 1)) for c in chunks
        }

        def update_parent_nodes(id: str, _chunks: dict[str, set[int]]):
            parent_lines = _chunks[id]
            child_chunks = {k: v for k, v in _chunks.items() if k.startswith(id + ".")}
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
                _chunks[id] = parent_lines
            return _chunks

        ids_longest_first = sorted(chunks, key=lambda x: len(x), reverse=True)
        for id in ids_longest_first:
            chunks = update_parent_nodes(id, chunks)

        output = []
        if chunks:
            # Generate a 'BASE chunk' with all lines not already part of a chunk
            base_chunk_lines = set(range(1, len(file_lines) + 1))
            for lines in chunks.values():
                base_chunk_lines -= lines
            lines_ref = lines_set_to_ref(base_chunk_lines)
            ref = f"{file}:{lines_ref}" if lines_ref else file
            base_chunk = {"id": f"{file}:BASE", "ref": ref}
            output.append(base_chunk)

        # Convert to refs and return
        for id, lines in chunks.items():
            lines_ref = lines_set_to_ref(lines)
            ref = f"{file}:{lines_ref}" if lines_ref else file
            output.append({"id": id, "ref": ref})
        return output
