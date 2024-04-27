import asyncio
import json
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional

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
        self, file: str, file_lines: list[str], verbose: bool
    ) -> list[dict[str, str]]:
        tries: int = 1
        for tries in range(tries, 0, -1):
            tries -= 1
            numbered_lines = "\n".join(
                f"{i+1}:{line}" for i, line in enumerate(file_lines)
            )
            file_message = f"{file}\n{numbered_lines}"
            chunks = await self.get_llm_response(file_message)
            if not chunks or all(is_chunk_valid(chunk) for chunk in chunks):
                return chunks
            if tries > 1 and verbose:
                print(f"Error with chunker response:\n{chunks}.\n{tries} tries left.")
        return []
