import asyncio
import json
from json.decoder import JSONDecodeError
from typing import Any, Coroutine, Dict, List, Optional

from spice import SpiceMessages

from ragdaemon.annotators.chunker import Chunker, is_chunk_valid
from ragdaemon.errors import RagdaemonError


semaphore = asyncio.Semaphore(50)


class ChunkerLLM(Chunker):
    name = "chunker_llm"
    chunk_field_id = "chunks_llm"

    async def get_llm_response(
        self,
        file_message: str,
        last_chunk: Optional[dict[str, Any]] = None,
        depth: int = 0,
    ) -> List[Dict[str, Any]]:
        if depth > 25:
            raise RagdaemonError("Maximum recursion depth reached for chunker.")
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")
        global semaphore
        async with semaphore:
            messages = SpiceMessages(self.spice_client)
            messages.add_system_prompt(name="chunker_llm.base")
            if last_chunk == None:
                messages.add_system_prompt(name="chunker_llm.first_pass")
            else:
                messages.add_system_prompt(
                    name="chunker_llm.next_pass",
                    last_chunk=json.dumps(last_chunk, indent=4),
                )
            messages.add_user_message(file_message)

            response = await self.spice_client.get_response(
                messages=messages,
                response_format={"type": "json_object"},
            )
            try:
                return json.loads(response.text)["chunks"]
            except JSONDecodeError:
                # This probably means the output is too long, i.e. there are too many
                # functions to chunk in one pass. We parse what we can and then recall to finish the job.
                index = response.text.rfind("}")
                fixed_json = response.text[: index + 1] + "]}"
                chunks = json.loads(fixed_json)["chunks"]
                new_chunks = await self.get_llm_response(
                    file_message, last_chunk=chunks[-1], depth=depth + 1
                )
                seen = set(chunk["id"] for chunk in chunks)
                for chunk in new_chunks:
                    if chunk["id"] not in seen:
                        chunks.append(chunk)
                        seen.add(chunk["id"])
                return chunks

    async def chunk_file(
        self, file_lines: list[str], file: str
    ) -> list[dict[str, Any]]:
        """Parse file_lines into a list of {id, ref} chunks."""
        chunks = list[dict[str, Any]]()

        # Get raw llm output
        tries: int = 1
        for tries in range(tries, 0, -1):
            tries -= 1
            numbered_lines = "\n".join(
                f"{i+1}:{line}" for i, line in enumerate(file_lines)
            )
            file_message = f"{file}\n{numbered_lines}"
            _chunks = await self.get_llm_response(file_message)
            if not _chunks or all(is_chunk_valid(chunk) for chunk in _chunks):
                chunks = _chunks
                break
            if tries > 1 and self.verbose:
                print(f"Error with chunker response:\n{chunks}.\n{tries} tries left.")
        if not chunks:
            return []
        if not all(is_chunk_valid(chunk) for chunk in chunks):
            raise ValueError(f"Invalid chunk data: {chunks}")

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
        return [base_chunk] + [
            {
                "id": chunk["id"],
                "ref": f"{file}:{chunk['start_line']}-{chunk['end_line']}",
            }
            for chunk in chunks
        ]
