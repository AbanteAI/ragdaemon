import asyncio

from spice import Spice, SpiceMessages
from spice.models import TextModel

from ragdaemon.graph import KnowledgeGraph


async def scan(
    nodes: list[str],
    graph: KnowledgeGraph,
    spice_client: Spice,
    summary_field_id: str,
    instruction: str,
    query: str,
    model: TextModel,
) -> list[str]:
    """Use an LLM to select relevant nodes from a list."""
    items = "\n".join(
        [
            f"{i+1}: {graph.nodes[child][summary_field_id]}"
            for i, child in enumerate(nodes)
        ]
    )

    def validator(text: str) -> bool:
        if not text:
            return True
        try:
            _ = [int(i) for i in text.split(",")]
            return True
        except ValueError:
            return False

    messages = SpiceMessages(spice_client)
    messages.add_system_prompt("locate.base")
    messages.add_user_prompt(
        "locate.user", instruction=instruction, query=query, items=items
    )
    response = await spice_client.get_response(
        messages=messages,
        model=model,
        validator=validator,
        retries=1,
    )

    selected = response.text
    if not selected:
        return []
    return [nodes[int(i) - 1] for i in selected.split(",")]


async def bfs(
    node: str,
    graph: KnowledgeGraph,
    edge_type: str,
    summary_field_id: str,
    spice_client: Spice,
    instruction: str,
    query: str,
    model: TextModel,
) -> list[str]:
    """Traverse the graph breadth-first and return relevant nodes."""
    child_nodes = [
        edge[1]
        for edge in graph.out_edges(node, data=True)
        if edge[-1].get("type") == edge_type
        and graph.nodes[edge[1]].get(summary_field_id) is not None
    ]
    if len(child_nodes) == 0:
        return [node]  # Leaf node (chunk or file)
    nodes = await scan(
        child_nodes, graph, spice_client, summary_field_id, instruction, query, model
    )
    if not nodes:
        return []
    tasks = [
        bfs(
            child,
            graph,
            edge_type,
            summary_field_id,
            spice_client,
            instruction,
            query,
            model,
        )
        for child in nodes
    ]
    results = await asyncio.gather(*tasks)
    return [node for result in results for node in result]


async def locate(
    graph: KnowledgeGraph,
    edge_type: str,
    summary_field_id: str,
    spice_client: Spice,
    instruction: str,
    query: str,
    model: TextModel,
    revise: bool = False,
) -> list[str]:
    """Use summaries to scan the codebase and return relevant nodes."""
    nodes = await bfs(
        "ROOT",
        graph,
        edge_type,
        summary_field_id,
        spice_client,
        instruction,
        query,
        model,
    )
    if revise:
        nodes = await scan(
            nodes, graph, spice_client, summary_field_id, instruction, query, model
        )
    return nodes
