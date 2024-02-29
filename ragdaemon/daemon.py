import asyncio
import json
import os
import subprocess
from pathlib import Path

from litellm import acompletion
import networkx as nx

from ragdaemon.utils import hash_str, ragdaemon_dir
from ragdaemon.database import get_db
from ragdaemon.viz.force_directed import fruchterman_reingold_3d


chunker_prompt = """\
Split the provided code file into chunks.
Return a list of functions, classes and methods in this code file as JSON data.
Each item in the list should contain:
1. `path` - a complete call path, e.g. `path/to/file:class.method`
2. `start_line` - where the function, class or method begins
3. `end_line` - where it ends - INCLUSIVE

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


class Daemon:
    """Build and maintain a searchable knowledge graph of codebase."""

    def __init__(self, cwd: Path, config: dict = {}):
        self.cwd = cwd
        self.config = config
        self.up_to_date = False
        self.error = None

        # Load or setup db
        count = get_db().count()
        print(f"Initialized database with {count} records.")

        # Load or initialize graph
        self.graph_path = ragdaemon_dir / "graph.json"
        self.graph_path.parent.mkdir(exist_ok=True)
        if self.graph_path.exists():
            with open(self.graph_path, "r") as f:
                data = json.load(f)
                self.graph = nx.readwrite.json_graph.node_link_graph(data)
                print(f"Loaded graph with {self.graph.number_of_nodes()} nodes.")
        else:
            self.graph = nx.MultiDiGraph()
            print(f"Initialized empty graph.")

    def save(self):
        """Saves the graph to disk."""
        data = nx.readwrite.json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"reefreshed knowledge graph saved to {self.graph_path}")

    async def refresh(self):
        """Iteratively updates graph by calling itself until graph is fully annotated."""
        # Determine current state
        git_paths = set(  # All non-ignored and untracked files
            Path(os.path.normpath(p))
            for p in filter(
                lambda p: p != "",
                subprocess.check_output(
                    ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                    cwd=self.cwd,
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).split("\n"),
            )
            if Path(self.cwd / p).exists()
        )
        checksums: dict[Path: str] = {}
        for path in git_paths:
            try:
                # could cache checksum by (path, last_updated) to save reads
                with open(self.cwd / path, "r") as f:
                    text = f.read()  
                document = f"{path}\n{text}"
                checksum = hash_str(document)
                if len(get_db().get(checksum)["ids"]) == 0:
                    # add new items to db (will generate embeddings)
                    metadatas = {
                        "id": str(path), 
                        "type": "file", 
                        "path": str(path), 
                        "checksum": checksum, 
                        "active": False
                    }
                    get_db().add(ids=checksum, documents=document, metadatas=metadatas)
                checksums[path] = checksum
            except UnicodeDecodeError:  # Ignore non-text files
                pass
            except Exception as e:
                print(f"Error processing path {path}: {e}")
        
        # Rebuild files if missing
        files_checksum = hash_str("".join(sorted(checksums.values())))
        if self.graph.graph.get("files_checksum") != files_checksum:        
            # Build graph and load from / add to db
            print(f"Refreshing file graph...")
            self.graph = nx.MultiDiGraph()
            edges_to_add = set()
            for path, checksum in checksums.items():
                # add db reecord
                node_id = str(path)
                db_record = get_db().get(checksum)
                record = db_record["metadatas"][0]
                self.graph.add_node(node_id, **record)
                # add hierarchy edges
                def _link_to_cwd(_path):
                    _parent = str(_path.parent) if len(_path.parts) > 1 else "ROOT"
                    edges_to_add.add((_parent, str(_path)))
                    if _parent != "ROOT":
                        _link_to_cwd(_path.parent)
                _link_to_cwd(path)
            # Add directory nodes with checksums
            for (source, target) in edges_to_add:
                for node_id in (source, target):
                    if node_id not in self.graph:
                        # add directories to graph (to link hierarchy) but not db
                        record = {"id": node_id, "type": "directory", "path": node_id}
                        self.graph.add_node(node_id, **record)
                self.graph.add_edge(source, target, type="hierarchy")
            self.graph.graph["files_checksum"] = files_checksum

        file_nodes = [
            (file, data) for file, data in self.graph.nodes(data=True) 
            if data["type"] == "file"
        ]

        # Add chunking data to file nodes
        semaphore = asyncio.Semaphore(20)
        async def _chunk_file_node(node, data) -> list[dict]:
            # Check for existing record
            if data.get("chunks"):
                if not isinstance(data["chunks"], list):
                    data["chunks"] = json.loads(data["chunks"])
                return
            # Get chunk data for file
            file_lines = (self.cwd / Path(node)).read_text().splitlines()
            if file_lines:  # Ignore empty files
                async with semaphore:
                    numbered_lines = "\n".join(f"{i+1}:{line}" for i, line in enumerate(file_lines))
                    file_message = (f"{node}\n{numbered_lines}")
                    messages = [
                        {"role": "system", "content": chunker_prompt},
                        {"role": "user", "content": file_message},
                    ]
                    response = await acompletion(
                        model="gpt-4-turbo-preview",
                        messages=messages,
                        response_format={ "type": "json_object" },
                    )
                    response = json.loads(response["choices"][0]["message"]["content"])
                    chunks = response.get("chunks", [])
            else:
                chunks = []
            if chunks:
                # Generate a 'BASE chunk' with all lines not already part of a chunk
                base_chunk_lines = set(range(1, len(file_lines) + 1))
                for chunk in chunks:
                    for i in range(chunk["start_line"], chunk["end_line"] + 1):
                        base_chunk_lines.discard(i)
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
                # Replace with standardized fields
                base_chunk = {"id": f"{node}:BASE", "path": f"{node}:{','.join(base_chunk_refs)}"}
                chunks = [
                    {"id": chunk["path"], "path": f"{node}:{chunk['start_line']}-{chunk['end_line']}"}
                    for chunk in chunks
                ] + [base_chunk]
            # Save to db and graph
            metadatas = get_db().get(data["checksum"])["metadatas"][0]
            metadatas["chunks"] = json.dumps(chunks)
            get_db().update(data["checksum"], metadatas=metadatas)
            data["chunks"] = chunks
        tasks = [_chunk_file_node(node, data) for node, data in file_nodes]
        await asyncio.gather(*tasks)

        # Load chunks from file node data
        for file, data in file_nodes:
            chunks = data["chunks"]
            if len(data["chunks"]) == 0:
                continue
            with open(Path(file), "r") as f:
                file_lines = f.readlines()
            edges_to_add = set()
            base_id = f"{file}:BASE"
            edges_to_add.add((file, base_id))
            for chunk in chunks:
                # Get the checksum record from database
                id = chunk["id"]
                text = ""
                lines_ref = chunk["path"].split(':')[1]
                ranges = lines_ref.split(',')
                for ref in ranges:
                    if '-' in ref:
                        _start, _end = ref.split('-')
                        text += "\n".join(file_lines[int(_start)-1:int(_end)])
                    else:
                        text += file_lines[int(ref)]
                document = f"{id}\n{text}"
                checksum = hash_str(document)
                records = get_db().get(checksum)["metadatas"]
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
                    get_db().add(ids=checksum, documents=document, metadatas=record)
                # Load into graph with edges
                self.graph.add_node(record["id"], **record)
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
                self.graph.add_edge(source, origin, type="hierarchy")

        # Recalculate positions (save to graph only, not db)
        if not all(
            data.get("layout", {}).get("hierarchy")
            for _, data in self.graph.nodes(data=True)
        ):
            print(f"Generating 3d layout for {self.graph.number_of_nodes()} nodes")
            pos = fruchterman_reingold_3d(self.graph)
            for node_id, coordinates in pos.items():
                if "layout" not in self.graph.nodes[node_id]:
                    self.graph.nodes[node_id]["layout"] = {}
                self.graph.nodes[node_id]["layout"]["hierarchy"] = coordinates

        self.save()

    def search(self, query: str):
        
        return get_db().query(query_texts=query)
