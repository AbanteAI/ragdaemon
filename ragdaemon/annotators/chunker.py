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


async def get_llm_response(file_message: str) -> dict:
    async with semaphore:
        messages = [
            {"role": "system", "content": chunker_prompt},
            {"role": "user", "content": file_message},
        ]
        response = await acompletion(
            model="gpt-4-turbo-preview",
            messages=messages,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    

def is_chunk_valid(chunk: dict) -> bool:
    # Includes the correct fields
    if not set(chunk.keys()) == {"id", "start_line", "end_line"}:
        return False
    # ID is in the correct format
    if not chunk["id"].count(":") == 1:
        return False
    # A chunk name is specified    
    if not len(chunk["id"].split(":")[1]):
        return False
    
    return True


async def get_file_chunk_data(cwd, node, data, verbose: bool = False) -> list[dict]:
    """Get or add chunk data to database, load into file data"""
    file_lines = (cwd / Path(node)).read_text().splitlines()
    if len(file_lines) == 0:
        chunks = []
    else:
        tries = 1
        for tries in range(tries, 0, -1):
            tries -= 1
            numbered_lines = "\n".join(
                f"{i+1}:{line}" for i, line in enumerate(file_lines)
            )
            file_message = f"{node}\n{numbered_lines}"
            response = await get_llm_response(file_message)
            chunks = response.get("chunks", [])
            if not chunks or all(is_chunk_valid(chunk) for chunk in chunks):
                break
            if verbose:
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
        base_chunk = {
            "id": f"{node}:BASE",
            "ref": f"{node}:{','.join(base_chunk_refs)}",
        }
        chunks = [
            {
                "id": chunk["id"],
                "ref": f"{node}:{chunk['start_line']}-{chunk['end_line']}",
            }
            for chunk in chunks
        ] + [base_chunk]
    # Save to db and graph
    metadatas = get_db(cwd).get(data["checksum"])["metadatas"][0]
    metadatas["chunks"] = json.dumps(chunks)
    get_db(cwd).update(data["checksum"], metadatas=metadatas)
    data["chunks"] = chunks


def add_file_chunks_to_graph(
    file: str, data: dict, graph: nx.MultiDiGraph, refresh: bool = False, verbose: bool = False
) -> dict[str:list]:
    """Load chunks from file data into db/graph"""
    cwd = Path(graph.graph["cwd"])
    add_to_db = {"ids": [], "documents": [], "metadatas": []}
    if not isinstance(data["chunks"], list):
        data["chunks"] = json.loads(data["chunks"])
    chunks = data["chunks"]
    if not refresh and len(data["chunks"]) == 0:
        return add_to_db
    edges_to_add = set()
    base_id = f"{file}:BASE"
    edges_to_add.add((file, base_id))
    for chunk in chunks:
        try:
            # Get the checksum record from database
            id = chunk["id"]
            ref = chunk["ref"]
            document = get_document(ref, cwd)
            checksum = hash_str(document)
            records = get_db(cwd).get(checksum)["metadatas"]
            if not refresh and len(records) > 0:
                record = records[0]
            else:
                record = {
                    "id": id,
                    "type": "chunk",
                    "ref": chunk["ref"],
                    "checksum": checksum,
                    "active": False,
                }
                add_to_db["ids"].append(checksum)
                add_to_db["documents"].append(document)
                add_to_db["metadatas"].append(record)
        except Exception as e:
            if verbose:
                print(f"Error processing chunk {chunk}: {e}")
            continue

        # Load into graph with edges
        graph.add_node(record["id"], **record)

        def _link_to_base_chunk(_id):
            path_str, chunk_str = _id.split(":")
            chunk_list = chunk_str.split(".")
            _parent = (
                f"{path_str}:{'.'.join(chunk_list[:-1])}"
                if len(chunk_list) > 1
                else base_id
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

    def __init__(self, *args, chunk_extensions: list[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunk_extensions = chunk_extensions

    def is_complete(self, graph: nx.MultiDiGraph) -> bool:
        for _, data in graph.nodes(data=True):
            if data.get("type") == "file" and data.get("chunks", None) is None:
                return False
        return True

    async def annotate(
        self, graph: nx.MultiDiGraph, refresh: bool = False
    ) -> nx.MultiDiGraph:
        cwd = Path(graph.graph["cwd"])
        file_nodes = [
            (file, data)
            for file, data in graph.nodes(data=True)
            if data.get("type") == "file"
        ]
        if self.chunk_extensions is not None:
            file_nodes = [
                (file, data)
                for file, data in file_nodes
                if Path(data["ref"]).suffix in self.chunk_extensions
            ]
        # Generate/add chunk data to file nodes
        tasks = []
        for node, data in file_nodes:
            if refresh or data.get("chunks", None) is None:
                tasks.append(get_file_chunk_data(cwd, node, data))
        if len(tasks) > 0:
            if self.verbose:
                await tqdm.gather(*tasks, desc="Chunking files...")
            else:
                await asyncio.gather(*tasks)
        # Load/Create chunk nodes into database and graph
        add_to_db = {"ids": [], "documents": [], "metadatas": []}
        for file, data in file_nodes:
            _add_to_db = add_file_chunks_to_graph(file, data, graph, verbose=self.verbose)
            for field, values in _add_to_db.items():
                add_to_db[field].extend(values)
        if len(add_to_db["ids"]) > 0:
            get_db(cwd).upsert(**add_to_db)
        return graph
