import numpy as np


def layout_force_directed(G):
    if not all(
        data.get("layout", {}).get("hierarchy")
        for _, data in G.nodes(data=True)
    ):
        print(f"Generating 3d layout for {G.number_of_nodes()} nodes")
        pos = fruchterman_reingold_3d(G)
        for node_id, coordinates in pos.items():
            if "layout" not in G.nodes[node_id]:
                G.nodes[node_id]["layout"] = {}
            G.nodes[node_id]["layout"]["hierarchy"] = coordinates
    return G        


def fruchterman_reingold_3d(G, iterations=40, repulsive_force=0.2, spring_length=0.2, dt=0.1):
    """Nodes repel, edges attract."""
    # Initialize node positions with random values
    pos = {node: data.get("layout", {}).get("hierarchy") for node, data in G.nodes(data=True)}
    if not all(pos.values()):
        pos = {node: np.random.rand(3) for node in G.nodes()}

    # Define force functions
    def repulsion_force(distance, k):
        return k ** 2 / distance

    def attraction_force(distance, k):
        return distance ** 2 / k

    # Main loop
    for iteration in range(iterations):
        # Calculate repulsive forces
        repulsive_forces = {node: np.zeros(3) for node in G.nodes()}
        for i, node1 in enumerate(G.nodes()):
            for j, node2 in enumerate(G.nodes()):
                if node1 != node2:
                    displacement = pos[node1] - pos[node2]
                    distance = np.linalg.norm(displacement) + 0.01  # Prevent division by zero
                    repulsive_forces[node1] += (displacement / distance) * repulsion_force(distance, repulsive_force)

        # Calculate attractive forces
        attractive_forces = {node: np.zeros(3) for node in G.nodes()}
        for edge in G.edges():
            node1, node2 = edge
            displacement = pos[node1] - pos[node2]
            distance = np.linalg.norm(displacement) + 0.01
            force = (displacement / distance) * attraction_force(distance, spring_length)
            attractive_forces[node1] -= force
            attractive_forces[node2] += force

        # Update positions
        for node in G.nodes():
            total_force = repulsive_forces[node] + attractive_forces[node]
            # Apply a simple cooling schedule to decrease the step size over iterations
            pos[node] += (total_force * dt) / np.linalg.norm(total_force + 0.01) * min(iteration / 10, 10)

    return {node: {'x': pos[node][0], 'y': pos[node][1], 'z': pos[node][2]} for node in G.nodes()}
