import asyncio
import json

from ragdaemon.annotators.chunker import Chunker, is_chunk_valid

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
3:import networkx as nx
4:
5:
6:class KnowledgeGraph:
7:    def __init__(self, cwd: Path):
8:        self.cwd = cwd
9:
10:_knowledge_graph = None
11:def get_knowledge_graph():
12:    global _knowledge_graph
13:    if _knowledge_graph is None:
14:        _knowledge_graph = KnowledgeGraph(Path.cwd())
15:    return _knowledge_graph
16:

RESPONSE:
{
    "chunks": [
        {"id": "src/graph.py:KnowledgeGraph", "start_line": 6, "end_line": 8},
        {"id": "src/graph.py:KnowledgeGraph.__init__", "start_line": 7, "end_line": 8},
        {"id": "src/graph.py:get_knowledge_graph", "start_line": 11, "end_line": 15}
    ]
}
--------------------------------------------------------------------------------
"""


semaphore = asyncio.Semaphore(50)


class ChunkerLLM(Chunker):
    name = "chunker_llm"

    async def get_llm_response(self, file_message: str) -> dict:
        global semaphore
        async with semaphore:
            messages = [
                {"role": "system", "content": chunker_prompt},
                {"role": "user", "content": file_message},
            ]
            response = await self.spice_client.get_response(
                messages=messages,
                response_format={"type": "json_object"},
            )
            return json.loads(response.text)

    async def chunk_file(
        self, file_id: str, file_lines: list[str], verbose=False, tries=1
    ) -> list[dict[str, str]]:
        for tries in range(tries, 0, -1):
            tries -= 1
            numbered_lines = "\n".join(
                f"{i+1}:{line}" for i, line in enumerate(file_lines)
            )
            file_message = f"{file_id}\n{numbered_lines}"
            response = await self.get_llm_response(file_message)
            chunks = response.get("chunks", [])
            if not chunks or all(is_chunk_valid(chunk) for chunk in chunks):
                return chunks
            if tries > 1 and verbose:
                print(f"Error with chunker response:\n{response}.\n{tries} tries left.")
        return []
