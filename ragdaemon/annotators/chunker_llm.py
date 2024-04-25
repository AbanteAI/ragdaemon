import asyncio
import json
from json.decoder import JSONDecodeError

from ragdaemon.annotators.chunker import Chunker, is_chunk_valid
from ragdaemon.errors import RagdaemonError
from spice import SpiceMessage

chunker_prompt = """\
Split the provided code file into chunks.
Return a list of functions, classes and methods in this code file as JSON data.
Each item in the list should contain:
1. `id` - the complete call path, e.g. `path/to/file:class.method`
2. `start_line` - where the function, class or method begins
3. `end_line` - where it ends - INCLUSIVE

If there are no chunks, return an empty list.

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


file_splitter_prompt = """\
Identify a good point in the provided code file to split it in half, and return the line 
number of that point.

You should choose a point which:
- Is approximately halfway through the file
- Is in between top-level functions or classes.

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
    "split_line": 7
}
--------------------------------------------------------------------------------
src/graph.py
1:import pathlib as Path
2:
3:
4:_knowledge_graph = None
5:class KnowledgeGraph:
6:    def __init__(self, cwd: Path):
7:        self.cwd = cwd
8:
9:    def get_knowledge_graph():
10:        global _knowledge_graph
11:        if _knowledge_graph is None:
12:            _knowledge_graph = KnowledgeGraph(Path.cwd())
13:        return _knowledge_graph
14:
15:def get_knowledge_graph():
16:    return _knowledge_graph

RESPONSE:
{
    "split_line": 14
}
"""


semaphore = asyncio.Semaphore(50)


class ChunkerLLM(Chunker):
    name = "chunker_llm"

    async def get_llm_response(self, file_message: str, depth: int = 1) -> dict:
        if depth > 3:
            raise RagdaemonError("Maximum recursion depth reached for chunker.")
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")
        global semaphore
        async with semaphore:
            messages: list[SpiceMessage] = [
                {"role": "system", "content": chunker_prompt},
                {"role": "user", "content": file_message},
            ]
            response = await self.spice_client.get_response(
                messages=messages,
                response_format={"type": "json_object"},
            )
            try:
                return json.loads(response.text)
            except JSONDecodeError:
                # This probably means the output is too long, i.e. there are too many
                # functions to chunk in one pass. We split it in half and try again.
                messages: list[SpiceMessage] = [
                    {"role": "system", "content": file_splitter_prompt},
                    {"role": "user", "content": file_message},
                ]
                response = await self.spice_client.get_response(
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                split_line = json.loads(response.text).get("split_line")
                if split_line is None:
                    raise RagdaemonError(
                        "Could not split file in half. Please try again."
                    )
                file_as_lines = file_message.split("\n")
                first_half = file_as_lines[:split_line]
                second_half = file_as_lines[split_line:]
                tasks = []
                tasks.append(self.get_llm_response("\n".join(first_half), depth + 1))
                tasks.append(self.get_llm_response("\n".join(second_half), depth + 1))
                responses = await asyncio.gather(*tasks)
                first_response, second_response = responses
                return {
                    "chunks": first_response.get("chunks", [])
                    + second_response.get("chunks", [])
                }

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
            response = await self.get_llm_response(file_message)
            chunks = response.get("chunks", [])
            if not chunks or all(is_chunk_valid(chunk) for chunk in chunks):
                return chunks
            if tries > 1 and verbose:
                print(f"Error with chunker response:\n{response}.\n{tries} tries left.")
        return []
