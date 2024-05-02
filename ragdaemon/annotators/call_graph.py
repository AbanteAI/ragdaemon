import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from tqdm.asyncio import tqdm
from spice import SpiceMessages
from spice.models import TextModel

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import (
    DEFAULT_CODE_EXTENSIONS,
    DEFAULT_COMPLETION_MODEL,
    parse_path_ref,
    semaphore,
)


def is_calls_valid(calls: dict[str, list[dict[str, str | list[int]]]]) -> bool:
    """Expected structure: {path/to/file:class.method: [1, 2, 3]}"""
    for target, lines in calls.items():
        if not target or not isinstance(target, str):
            return False
        if not lines or not isinstance(lines, list):
            return False
        if not all(isinstance(line, int) for line in lines):
            return False
    return True


class CallGraph(Annotator):
    name = "call_graph"
    call_field_id = "calls"

    def __init__(
        self,
        *args,
        call_extensions: Optional[list[str]] = None,
        chunk_field_id: Optional[str] = None,
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if call_extensions is None:
            call_extensions = DEFAULT_CODE_EXTENSIONS
        self.call_extensions = call_extensions
        if chunk_field_id is None:
            raise RagdaemonError("Chunk field ID is required for call graph annotator.")
        self.chunk_field_id = chunk_field_id
        self.model = model

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
                if not isinstance(calls, dict):
                    calls = json.loads(calls)
                for target, lines in calls.items():
                    if target not in graph:
                        return False
                    matching_edges = [
                        edge
                        for edge in graph.in_edges(target, data=True)
                        if edge[-1].get("type") == "call"
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

        async with semaphore:
            response = await self.spice_client.get_response(
                messages=messages,
                model=self.model,
                response_format={"type": "json_object"},
            )
        try:
            calls = json.loads(response.text)
        except json.JSONDecodeError:
            raise RagdaemonError("Failed to parse JSON response.")
        if not is_calls_valid(calls):
            raise RagdaemonError(f"Model returned malformed calls: {calls}")

        # Resolve library calls
        targets = set(calls.keys())
        unresolved = set()
        for target in targets:
            if target in graph:
                continue
            candidates = [
                node
                for node, data in graph.nodes(data=True)
                if data.get("type") == "chunk" and node.endswith(target)
            ]
            if len(candidates) != 1:
                del calls[target]
                unresolved.add(target)
            else:
                calls[candidates[0]] = calls.pop(target)
        if unresolved and self.verbose:
            path = document.split("\n")[0]
            print(f"Unresolved calls in {path}: {unresolved}")

        return calls

    async def get_file_call_data(
        self,
        node: str,
        data: dict,
        graph: KnowledgeGraph,
        db: Database,
        retries: int = 1,
    ):
        """Generate and save call data for a file node to graph and db"""
        calls = {}
        record = db.get(data["checksum"])
        document = record["documents"][0]

        # Insert line numbers
        lines = document.split("\n")
        file = lines[0]
        file_lines = lines[1:]
        if not file_lines or not any(line for line in file_lines):
            return calls
        file_lines = [f"{i+1}:{line}" for i, line in enumerate(file_lines)]
        document = "\n".join([file] + file_lines)

        for i in range(retries + 1, 0, -1):
            try:
                calls = await self.get_llm_response(document, graph)
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
        graph.remove_edges_from(
            [edge for edge in graph.edges(data=True) if edge[-1].get("type") == "call"]
        )
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
                tasks.append(self.get_file_call_data(node, data, graph, db))
        if len(tasks) > 0:
            if self.verbose:
                await tqdm.gather(*tasks, desc="Generating call graph")
            else:
                await asyncio.gather(*tasks)

        # Add call edges to graph. Each call should have only ONE source; if there are
        # chunks, the source is the matching chunk, otherwise it's the file.
        for file, data in files_with_calls:
            calls = data[self.call_field_id]
            if not isinstance(calls, dict):
                calls = json.loads(calls)
            if not calls:
                continue

            # Build an index of {line: node} for the file
            line_index = {}
            chunks = data.get(self.chunk_field_id)
            if chunks is None:
                raise RagdaemonError(f"File node {file} is missing chunks field.")
            if not isinstance(chunks, list):
                chunks = json.loads(chunks)
            if len(chunks) == 0:
                checksum = data.get("checksum")
                if checksum is None:
                    raise RagdaemonError(f"File node {file} is missing checksum field.")
                record = db.get(checksum)
                document = record["documents"][0]
                for i in range(1, len(document.split("\n")) + 1):
                    line_index[i] = file
            else:
                for chunk in chunks:
                    _, lines = parse_path_ref(chunk["ref"])
                    if lines is None:
                        raise RagdaemonError(f"Chunk {chunk} is missing line numbers.")
                    for line in lines:
                        line_index[line] = chunk["id"]

            # Add one edge per source/target pair
            for target, lines in calls.items():
                sources = set()
                for line in lines:
                    if line not in line_index:
                        raise RagdaemonError(f"Line {line} not found in {file}.")
                    sources.add(line_index[line])
                for source in sources:
                    graph.add_edge(source, target, type="call")

        return graph
