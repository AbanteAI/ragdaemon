import numpy as np
from tqdm import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError


def fruchterman_reingold_3d(
    G,
    iterations=40,
    repulsive_force=0.2,
    spring_length=0.2,
    dt=0.1,
    verbose: bool = False,
):
    # Initialize node positions with random values
    pos = {
        node: data.get("layout", {}).get("hierarchy")
        for node, data in G.nodes(data=True)
    }
    if not all(pos.values()):
        pos = {node: np.random.rand(3) for node in G.nodes()}

    # Define force functions
    def repulsion_force(distance, k):
        return k**2 / distance

    def attraction_force(distance, k):
        return distance**2 / k

    def iterate(iteration: int):
        # Calculate repulsive forces
        repulsive_forces = {node: np.zeros(3) for node in G.nodes()}
        for i, node1 in enumerate(G.nodes()):
            for j, node2 in enumerate(G.nodes()):
                if node1 != node2:
                    displacement = pos[node1] - pos[node2]
                    distance = (
                        np.linalg.norm(displacement) + 0.01
                    )  # Prevent division by zero
                    repulsive_forces[node1] += (
                        displacement / distance
                    ) * repulsion_force(distance, repulsive_force)

        # Calculate attractive forces
        attractive_forces = {node: np.zeros(3) for node in G.nodes()}
        for edge in G.edges():
            node1, node2 = edge
            displacement = pos[node1] - pos[node2]
            distance = np.linalg.norm(displacement) + 0.01
            force = (displacement / distance) * attraction_force(
                distance, spring_length
            )
            attractive_forces[node1] -= force
            attractive_forces[node2] += force

        # Update positions
        for node in G.nodes():
            total_force = repulsive_forces[node] + attractive_forces[node]
            # Apply a simple cooling schedule to decrease the step size over iterations
            pos[node] += (
                (total_force * dt)
                / np.linalg.norm(total_force + 0.01)
                * min(iteration / 10, 10)
            )

    # Main loop
    if verbose:
        for iteration in tqdm(
            range(iterations), desc="Generating hierarchical layout..."
        ):
            iterate(iteration)
    else:
        for iteration in range(iterations):
            iterate(iteration)

    return {
        node: {"x": pos[node][0], "y": pos[node][1], "z": pos[node][2]}
        for node in G.nodes()
    }


class LayoutHierarchy(Annotator):
    name = "layout_hierarchy"

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        # Check that they have data.layout.hierarchy
        for node, data in graph.nodes(data=True):
            if data is None:
                raise RagdaemonError(f"Node {node} has no data.")
            if not data.get("layout", {}).get("hierarchy"):
                return False
        return True

    async def annotate(
        self,
        graph: KnowledgeGraph,
        db: Database,
        refresh: bool = False,
        iterations: int = 40,
    ) -> KnowledgeGraph:
        """
        a. Regenerate x/y/z for all nodes
        b. Update all nodes
        c. Save to chroma
        """
        pos = fruchterman_reingold_3d(
            graph, iterations=iterations, verbose=self.verbose
        )
        for node_id, coordinates in pos.items():
            node = graph.nodes[node_id]
            if "layout" not in node:
                node["layout"] = {}
            node["layout"]["hierarchy"] = coordinates
        return graph
