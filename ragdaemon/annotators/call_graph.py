"""
Generate a list of calls to (1) library and (2) dependency functions,
and the line on which the call occurs, for each file.

{
    "library": [
        {"target": "function_name", "lines": [1, 2, 3]},
    ],
    "dependency": [
        {"target": "package_name.function_name", "lines": [4, 5, 6]},
    ],
}

The callee (function being called) should match an existing node in the
graph, and dependencies should point to their package name.

We run this and save it to the FILE to avoid duplicate calls and give
it the best chance of resolving callees/dependencies.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import DEFAULT_CODE_EXTENSIONS
from spice import SpiceMessages


def is_calls_valid(calls: dict[str, list[dict[str, str | list[int]]]]) -> bool:
    if any(k not in {"library", "dependency"} for k in calls.keys()):
        return False
    merged = calls.get("library", []) + calls.get("dependency", [])
    for call in merged:
        target = call.get("target")
        lines = call.get("lines")
        if not target or not isinstance(target, str):
            return False
        if not lines or not isinstance(lines, list):
            return False
        if not all(isinstance(line, int) for line in lines):
            return False
    return True


semaphore = asyncio.Semaphore(50)


class CallGraph(Annotator):
    name = "call_graph"
    call_field_id = "calls"

    def __init__(self, *args, call_extensions: Optional[list[str]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        if call_extensions is None:
            call_extensions = DEFAULT_CODE_EXTENSIONS
        self.call_extensions = call_extensions


    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") != "file":
                continue
            calls = data.get(self.call_field_id, None)
            if calls is None:
                if self.call_extensions is None:
                    return False
                extension = Path(data["ref"]).suffix
                if extension in self.call_extensions:
                    return False
            else:
                if not isinstance(calls, list):
                    calls = json.loads(calls)
                for call in calls:
                    target = call.get("target")
                    lines = call.get("lines")
                    if target not in graph:
                        return False
                    matching_edges = [
                        edge for edge in graph.in_edges(target, data=True)
                        if edge[3].get("type") == "call"
                        if edge[0].startswith(node)
                    ]
                    if len(matching_edges) != len(lines):
                        return False
        return True


    async def get_llm_response(self, document: str, graph: KnowledgeGraph) -> str:
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")
        
        messages = SpiceMessages(self.spice_client)
        messages.add_system_prompt(name="call_graph.base")
        messages.add_user_prompt("call_graph.user", document=document)
        
        global semaphore
        async with semaphore:
            response = await self.spice_client.get_response(
                messages=messages,
                response_format={"type": "json_object"},
            )
        try:
            calls = json.loads(response.text)
        except json.JSONDecodeError:
            raise RagdaemonError("Failed to parse JSON response.")
        if not is_calls_valid(calls, graph):
            raise RagdaemonError(f"Model returned malformed calls: {calls}")
        
        # Resolve library calls
        for target in calls.get("library", {}).keys():
            if target in graph:
                continue
            candidates = [
                node for node, data in graph.nodes(data=True) 
                if data.get("type") == "function" and node.endswith(target)
            ]
            if len(candidates) != 1:
                raise RagdaemonError(f"Failed to resolve target {target}.")
            calls["library"][candidates[0]] = calls["library"].pop(target)

        return calls
    
    async def get_file_call_data(
        self, node: str, data: dict, db: Database, retries: int = 1
    ):
        """Generate and save call data for a file node to graph and db"""
        calls = []
        record = db.get(data["checksum"])
        document = record["documents"][0]
        for i in range(retries + 1, 0, -1):
            try:
                calls = await self.get_llm_response(document, self.graph)
                break
            except RagdaemonError as e:
                if self.verbose:
                    print(
                        f"Error generating call graph for {node}:\n{e}\n"
                        + f"{i-1} retries left."
                        if i > 1
                        else "Skipping."
                    )
                
        # Save to db and graph
        metadatas = record["metadatas"][0]
        metadatas[self.call_field_id] = json.dumps(calls)
        db.update(data["checksum"], metadatas=metadatas)
        data[self.call_field_id] = calls

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        # Remove any existing call edges
        graph.remove_edges_from([
            edge for edge in graph.edges(data=True) if edge[3].get("type") == "call"
        ])
        # Get the list of nodes expected to have calls data
        files_with_calls = list[tuple[str, dict[str, Any]]]()
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if data.get("type") != "file":
                continue
            if self.call_extensions is None:
                files_with_calls.append(node)
            else:
                extension = Path(data["ref"]).suffix
                if extension in self.call_extensions:
                    files_with_calls.append((node, data))
        # Generate/add call data for nodes that don't have it
        tasks = []
        for node, data in files_with_calls:
            if refresh or data.get(self.call_field_id, None) is None:
                checksum = data.get("checksum")
                if checksum is None:
                    raise RagdaemonError(f"Node {node} has no checksum.")
                tasks.append(self.get_llm_response(node, graph))
        if len(tasks) > 0:
            if self.verbose:
                await asyncio.gather(*tasks, desc="Generating call graph")
            else:
                await asyncio.gather(*tasks)

        # Add call edges to graph
        for file, data in files_with_calls:
            calls = data[self.call_field_id]
            # Add library calls from source(s) to target
            
