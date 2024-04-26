import asyncio
import json
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional

from spice import SpiceMessage

from ragdaemon.annotators.chunker import Chunker, is_chunk_valid
from ragdaemon.errors import RagdaemonError

first_pass = "Make sure to start at the beginning of the file and do it in order!"
next_pass = """\
You are continuing this task from a previous call. Start exactly where the previous call stopped, output the last chunk as the first chunk of your new output, and finish the rest of the file after that chunk.
Here is the last chunk already parsed, that you will start with:\n"""

chunker_prompt = """\
Split the provided code file into chunks.
Return a list of functions, classes and methods in this code file as JSON data.
Each item in the list should contain:
1. `id` - the complete call path, e.g. `path/to/file:class.method`
2. `start_line` - where the function, class or method begins
3. `end_line` - where it ends - INCLUSIVE

If there are no chunks, return an empty list. {{ pass }}

EXAMPLE:
--------------------------------------------------------------------------------
src/graph.py
1:import pathlib as Path
2:
3:
4:class KnowledgeGraph:
5:    def __init__(self, cwd: Path):
6:        self.cwd = cwd
7:
8:_knowledge_graph = None
9:def get_knowledge_graph():
10:    global _knowledge_graph
11:    if _knowledge_graph is None:
12:        _knowledge_graph = KnowledgeGraph(Path.cwd())
13:    return _knowledge_graph
14:

RESPONSE:
{
    "chunks": [
        {"id": "src/graph.py:KnowledgeGraph", "start_line": 4, "end_line": 6},
        {"id": "src/graph.py:KnowledgeGraph.__init__", "start_line": 5, "end_line": 6},
        {"id": "src/graph.py:get_knowledge_graph", "start_line": 9, "end_line": 13}
    ]
}
--------------------------------------------------------------------------------
"""

semaphore = asyncio.Semaphore(50)


class ChunkerLLM(Chunker):
    name = "chunker_llm"

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
            if last_chunk == None:
                prompt = chunker_prompt.replace("{{ pass }}", first_pass)
            else:
                prompt = chunker_prompt.replace(
                    "{{ pass }}", next_pass + json.dumps(last_chunk, indent=4)
                )

            messages: list[SpiceMessage] = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": file_message},
            ]
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
