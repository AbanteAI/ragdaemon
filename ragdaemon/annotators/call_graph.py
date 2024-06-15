import asyncio
import json
from functools import partial
from pathlib import Path
from typing import Any, Optional

from spice import SpiceMessages
from spice.models import TextModel
from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database, remove_update_db_duplicates
from ragdaemon.errors import RagdaemonError
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.utils import (
    DEFAULT_CODE_EXTENSIONS,
    DEFAULT_COMPLETION_MODEL,
    match_refresh,
    parse_path_ref,
    semaphore,
)


class CallGraph(Annotator):
    name = "call_graph"
    call_field_id = "calls"

    def __init__(
        self,
        *args,
        call_extensions: Optional[list[str]] = None,
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        pipeline: dict[str, Annotator] = {},
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if call_extensions is None:
            call_extensions = DEFAULT_CODE_EXTENSIONS
        self.call_extensions = call_extensions
        try:
            chunk_field_id = next(
                getattr(a, "chunk_field_id")
                for a in pipeline.values()
                if "chunker" in a.name
            )
        except (StopIteration, AttributeError):
            raise RagdaemonError(
                "CallGraph annotator requires a 'chunker' annotator with chunk_field_id."
            )
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

    async def get_llm_response(
        self, document: str, graph: KnowledgeGraph
    ) -> dict[str, list[int]]:
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")

        messages = SpiceMessages(self.spice_client)
        messages.add_system_prompt(name="call_graph.base")
        messages.add_user_prompt("call_graph.user", document=document)

        def validate(response: str, max_line: int) -> bool:
            """Expected structure: {path/to/file:class.method: [1, 2, 3]}"""
            try:
                calls = json.loads(response)
            except json.JSONDecodeError:
                return False
            for target, lines in calls.items():
                if not target or not isinstance(target, str):
                    return False
                if not lines or not isinstance(lines, list):
                    return False
                if not all(isinstance(line, int) for line in lines):
                    return False
                if any(line > max_line for line in lines):
                    return False
            return True

        validator = partial(validate, max_line=len(document.split("\n")))
        async with semaphore:
            try:
                response = await self.spice_client.get_response(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                    validator=validator,
                    retries=2,
                )
            except ValueError:  # Raised after all retries fail
                if self.verbose > 0:
                    file = document.split("\n")[0]
                    print(
                        f"Failed to generate call graph for {file} after 3 tries, Skipping."
                    )
                return {}

        calls = json.loads(response.text)

        # Resolve library calls
        targets = set(calls.keys())
        unresolved = set()
        """
        TODO: Handle unresolved calls. Usually result from:
        - Class inheritance. No method for resolving.
        - Missing file extensions. Imports can be unclear which part is the file.
        - Using '.' instead of '/' in the path definition. Again, imports.
        """
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

        return calls

    async def get_file_call_data(
        self,
        node: str,
        data: dict,
        graph: KnowledgeGraph,
        retries: int = 1,
    ):
        """Generate and save call data for a file node to graph"""
        calls = {}
        document = data["document"]

        # Insert line numbers
        lines = document.split("\n")
        file = lines[0]
        file_lines = lines[1:]
        if any(line for line in file_lines):
            file_lines = [f"{i+1}:{line}" for i, line in enumerate(file_lines)]
            document = "\n".join([file] + file_lines)

            for i in range(retries + 1, 0, -1):
                try:
                    calls = await self.get_llm_response(document, graph)
                    break
                except RagdaemonError as e:
                    if self.verbose > 1:
                        print(
                            f"Error generating call graph for {node}:\n{e}\n"
                            + f"{i-1} retries left."
                            if i > 1
                            else "Skipping."
                        )

        data[self.call_field_id] = calls

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: str | bool = False
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
        files_just_updated = set()
        for node, data in files_with_calls:
            if (
                match_refresh(refresh, node)
                or data.get(self.call_field_id, None) is None
            ):
                checksum = data.get("checksum")
                if checksum is None:
                    raise RagdaemonError(f"Node {node} has no checksum.")
                tasks.append(self.get_file_call_data(node, data, graph))
                files_just_updated.add(node)
        if len(tasks) > 0:
            if self.verbose > 1:
                await tqdm.gather(*tasks, desc="Generating call graph")
            else:
                await asyncio.gather(*tasks)
            update_db = {"ids": [], "metadatas": []}
            for node in files_just_updated:
                data = graph.nodes[node]
                update_db["ids"].append(data["checksum"])
                metadatas = {self.call_field_id: json.dumps(data[self.call_field_id])}
                update_db["metadatas"].append(metadatas)
            update_db = remove_update_db_duplicates(**update_db)
            db.update(**update_db)

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
                document = data["document"]
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
