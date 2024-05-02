import asyncio
import json
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional

from spice import SpiceMessages
from spice.models import TextModel

from ragdaemon.annotators.chunker import Chunker
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import DEFAULT_COMPLETION_MODEL, lines_set_to_ref, semaphore


def is_chunk_valid(chunk: dict, last_valid_line: int):
    if not set(chunk.keys()) == {"id", "start_line", "end_line"}:
        raise RagdaemonError(f"Chunk is missing fields: {chunk}")
    halves = chunk["id"].split(":")
    if len(halves) != 2 or not halves[0] or not halves[1]:
        raise RagdaemonError(f"Chunk ID is not in the correct format: {chunk}")
    start, end = chunk.get("start_line"), chunk.get("end_line")
    if start is None or end is None:
        raise RagdaemonError(f"Chunk lines are missing: {chunk}")
    # Sometimes output is int, sometimes string. This accomodates either.
    start, end = str(start), str(end)
    if not start.isdigit() or not end.isdigit():
        raise RagdaemonError(f"Chunk lines are not valid: {chunk}")
    start, end = int(start), int(end)
    if not 1 <= start <= end <= last_valid_line:
        raise RagdaemonError(f"Chunk lines are out of bounds: {chunk}")
    # TODO: Validate the ref, i.e. a parent chunk exists


class ChunkerLLM(Chunker):
    name = "chunker_llm"
    chunk_field_id = "chunks_llm"

    def __init__(
        self,
        *args,
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.model = model

    async def get_llm_response(
        self,
        file: str,
        file_lines: list[str],
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

        async with semaphore:
            response = await self.spice_client.get_response(
                messages=messages,
                model=self.model,
                response_format={"type": "json_object"},
            )
        try:
            chunks = json.loads(response.text)["chunks"]
        except JSONDecodeError:
            raise RagdaemonError(
                "Failed to parse JSON response. This could mean that the output is too "
                "long, i.e. there are too many functions to chunk in one pass. If this "
                "is the case, decrease the batch size and try again."
            )
        last_valid_line = int(file_lines[-1].split(":")[0])
        for chunk in chunks:
            is_chunk_valid(chunk, last_valid_line)
        if last_chunk is not None:
            if not any(chunk["id"] == last_chunk["id"] for chunk in chunks):
                raise RagdaemonError(
                    f"Last chunk replacement ({last_chunk['id']}) not found in response."
                )
        return chunks

    async def chunk_document(
        self, document: str, batch_size: int = 1000, retries: int = 1
    ) -> list[dict[str, Any]]:
        """Parse file_lines into a list of {id, ref} chunks."""
        lines = document.split("\n")
        file = lines[0]
        file_lines = lines[1:]
        if not file_lines or not any(line for line in file_lines):
            return []
        file_lines = [f"{i+1}:{line}" for i, line in enumerate(file_lines)]

        # Get raw llm output: {id, start_line, end_line}
        chunks = list[dict[str, Any]]()
        n_batches = (len(file_lines) + batch_size - 1) // batch_size
        for i in range(n_batches):
            batch_lines = file_lines[i * batch_size : (i + 1) * batch_size]
            last_chunk = chunks.pop() if chunks else None
            for j in range(retries + 1, 0, -1):
                try:
                    _chunks = await self.get_llm_response(file, batch_lines, last_chunk)
                    chunks.extend(_chunks)
                    break
                except RagdaemonError as e:
                    if self.verbose:
                        print(
                            f"Error chunking {file} batch {i+1}/{n_batches}:\n{e}\n"
                            + f"{j-1} retries left."
                            if j > 1
                            else "Skipping."
                        )
                    if j == 1:
                        return []

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
                end_line = max(max(v) for v in child_chunks.values())
                parent_lines = set(range(start_line, end_line + 1))
                # Remove child lines from parent lines
                for child_lines in child_chunks.values():
                    parent_lines -= child_lines
                _chunks[id] = parent_lines
            return _chunks

        ids_longest_first = sorted(chunks, key=lambda x: len(x), reverse=True)
        for id in ids_longest_first:
            chunks = update_parent_nodes(id, chunks)

        # Generate a 'BASE chunk' with all lines not already part of a chunk
        base_chunk_lines = set(range(1, len(file_lines) + 1))
        for lines in chunks.values():
            base_chunk_lines -= lines
        lines_ref = lines_set_to_ref(base_chunk_lines)
        ref = f"{file}:{lines_ref}" if lines_ref else file
        base_chunk = {"id": f"{file}:BASE", "ref": ref}

        # Convert to refs and return
        output = [base_chunk]
        for id, lines in chunks.items():
            lines_ref = lines_set_to_ref(lines)
            ref = f"{file}:{lines_ref}" if lines_ref else file
            output.append({"id": id, "ref": ref})
        return output
