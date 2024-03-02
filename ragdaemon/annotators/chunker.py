import asyncio
import json
from pathlib import Path

import networkx as nx
from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.utils import hash_str, get_document
from ragdaemon.database import get_db
from ragdaemon.llm import acompletion


chunker_prompt = """\
Split the provided code file into chunks.
Return a list of functions, classes and methods in this code file as JSON data.
Each item in the list should contain:
1. `path` - a complete call path, e.g. `path/to/file:class.method`
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
        {"path": "src/graph.py:KnowledgeGraph", "start_line": 6, "end_line": 8},
        {"path": "src/graph.py:KnowledgeGraph.__init__", "start_line": 7, "end_line": 8},
        {"path": "src/graph.py:get_knowledge_graph", "start_line": 11, "end_line": 15}
    ]
}
--------------------------------------------------------------------------------
"""


semaphore = asyncio.Semaphore(20)
async def get_llm_response(file_message: str) -> dict:
    async with semaphore:
        messages = [
            {"role": "system", "content": chunker_prompt},
            {"role": "user", "content": file_message},
        ]
        response = await acompletion(
            model="gpt-4-turbo-preview",
            messages=messages,
            response_format={ "type": "json_object" },
        )
        return json.loads(response.choices[0].message.content)
    

async def get_file_chunk_data(cwd, node, data) -> list[dict]:
    """Get or add chunk data to database, load into file data"""
    file_lines = (cwd / Path(node)).read_text().splitlines()
    if len(file_lines) == 0:
        chunks = []
    else:
        tries = 3
        for tries in range(tries, 0, -1):
            tries -= 1
            numbered_lines = "\n".join(f"{i+1}:{line}" for i, line in enumerate(file_lines))
            file_message = (f"{node}\n{numbered_lines}")
            response = await get_llm_response(file_message)
            chunks = response.get("chunks", [])
            if not chunks or all(
                set(chunk.keys()) == {"path", "start_line", "end_line"}
                and chunk["path"].count(":") == 1
                for chunk in chunks
            ):
                break
            print(f"Error with chunker response:\n{response}.\n{tries} tries left.")
            chunks = []
    if chunks:
        # Generate a 'BASE chunk' with all lines not already part of a chunk
        base_chunk_lines = set(range(1, len(file_lines) + 1))
        for chunk in chunks:
            for i in range(chunk["start_line"], chunk["end_line"] + 1):
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
        # Replace with standardized fields
        base_chunk = {"id": f"{node}:BASE", "path": f"{node}:{','.join(base_chunk_refs)}"}
        chunks = [
            {"id": chunk["path"], "path": f"{node}:{chunk['start_line']}-{chunk['end_line']}"}
            for chunk in chunks
        ] + [base_chunk]
    # Save to db and graph
    metadatas = get_db(cwd).get(data["checksum"])["metadatas"][0]
    metadatas["chunks"] = json.dumps(chunks)
    get_db(cwd).update(data["checksum"], metadatas=metadatas)
    data["chunks"] = chunks


def add_file_chunks_to_graph(file: str, data: dict, graph: nx.MultiDiGraph) -> dict[str: list]:
    """Load chunks from file data into db/graph"""
    cwd = Path(graph.graph["cwd"])
    add_to_db = {"ids": [], "documents": [], "metadatas": []}
    if not isinstance(data["chunks"], list):
        data["chunks"] = json.loads(data["chunks"])
    chunks = data["chunks"]
    if len(data["chunks"]) == 0:
        return add_to_db
    with open(cwd / file, "r") as f:
        file_lines = f.readlines()
    edges_to_add = set()
    base_id = f"{file}:BASE"
    edges_to_add.add((file, base_id))
    for chunk in chunks:
        # Get the checksum record from database
        id = chunk["id"]
        path = chunk["path"]
        document = get_document(path, cwd, file_lines)
        checksum = hash_str(document)
        records = get_db(cwd).get(checksum)["metadatas"]
        if len(records) > 0:
            record = records[0]
        else:
            record = {
                "id": id, 
                "type": "chunk", 
                "path": chunk["path"],
                "checksum": checksum, 
                "active": False
            }
            add_to_db["ids"].append(checksum)
            add_to_db["documents"].append(document)
            add_to_db["metadatas"].append(record)
        # Load into graph with edges
        graph.add_node(record["id"], **record)
        def _link_to_base_chunk(_id):
            file_path, chunk_path = _id.split(':')
            chunk_stack = chunk_path.split('.')
            _parent = (
                f"{file_path}:{'.'.join(chunk_stack[:-1])}" if len(chunk_stack) > 1 else base_id
            )
            edges_to_add.add((_parent, _id))
            if _parent != base_id:
                _link_to_base_chunk(_parent)
        _link_to_base_chunk(id)
    for source, origin in edges_to_add:
        graph.add_edge(source, origin, type="hierarchy")
    return add_to_db


class Chunker(Annotator):
    name = "chunker"

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        for _, data in graph.nodes(data=True):
            if data.get("type") == "file" and data.get("chunks", None) is None:
                return False
        return True
    
    async def annotate(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        cwd = Path(graph.graph["cwd"])
        file_nodes = [
            (file, data) for file, data in graph.nodes(data=True) 
            if data.get("type") == "file"
        ]
        # Generate/add chunk data to file nodes
        tasks = []
        for node, data in file_nodes:
            if data.get("chunks", None) is None:
                tasks.append(get_file_chunk_data(cwd, node, data))
        if len(tasks) > 0:
            print(f"Chunking {len(tasks)} files...")
            await tqdm.gather(*tasks)
        # Load/Create chunk nodes into database and graph
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for file, data in file_nodes:
            _add_to_db = add_file_chunks_to_graph(file, data, graph)
            for field, values in _add_to_db.items():
                add_to_db[field].extend(values)
        if len(add_to_db["ids"]) > 0:
            get_db(cwd).add(**add_to_db)
        return graph
