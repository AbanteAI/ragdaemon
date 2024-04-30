import asyncio
import json
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional

from spice import SpiceMessages

from ragdaemon.annotators.chunker import Chunker
from ragdaemon.errors import RagdaemonError


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


semaphore = asyncio.Semaphore(100)


class ChunkerLLM(Chunker):
    name = "chunker_llm"
    chunk_field_id = "chunks_llm"

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

        global semaphore
        async with semaphore:
            response = await self.spice_client.get_response(
                messages=messages,
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
        lines = document.splitlines()
        file = lines[0]
        file_lines = lines[1:]
        if not file_lines or not any(line for line in file_lines):
            return []
        file_lines = [f"{i+1}:{line}" for i, line in enumerate(file_lines)]

        # Get raw llm output
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

        # Make sure end_line of each 'parent' chunk covers all children
        def update_end_lines(id: str, _chunks: list[dict[str, Any]]):
            child_chunks = [c for c in _chunks if c["id"].startswith(id + ".")]
            if child_chunks:
                end_line = max(c["end_line"] for c in child_chunks)
                parent_chunk = next(c for c in _chunks if c["id"] == id)
                parent_chunk["end_line"] = end_line
            return _chunks

        for chunk in sorted(chunks, key=lambda c: len(c["id"]), reverse=True):
            chunks = update_end_lines(chunk["id"], chunks)

        # Generate a 'BASE chunk' with all lines not already part of a chunk
        base_chunk_lines = set(range(1, len(file_lines) + 1))
        for chunk in chunks:
            for i in range(int(chunk["start_line"]), int(chunk["end_line"]) + 1):
                base_chunk_lines.discard(i)
        if len(base_chunk_lines) > 0:
            base_chunk_lines_sorted = sorted(list(base_chunk_lines))
            base_chunk_refs = []
            start = base_chunk_lines_sorted[0]
            end = start
            for i in base_chunk_lines_sorted[1:]:
                if i == end + 1:
                    end = i
                else:
                    if start == end:
                        base_chunk_refs.append(f"{start}")
                    else:
                        base_chunk_refs.append(f"{start}-{end}")
                    start = end = i
            base_chunk_refs.append(f"{start}-{end}")
        else:
            base_chunk_refs = []
        lines_str = ":" + ",".join(base_chunk_refs) if base_chunk_refs else ""
        base_chunk = {"id": f"{file}:BASE", "ref": f"{file}{lines_str}"}

        # Convert to refs and return
        output = [base_chunk]
        for chunk in chunks:
            if chunk["start_line"] == chunk["end_line"]:
                lines_str = str(chunk["start_line"])
            else:
                lines_str = f"{chunk['start_line']}-{chunk['end_line']}"
            output.append({"id": chunk["id"], "ref": f"{file}:{lines_str}"})
        return output
