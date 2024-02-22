from math import sqrt

import networkx as nx


def add_coordiantes_to_graph(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    # Add x, y coordiantes with spring layout
    pos = nx.spring_layout(G)
    for node in G.nodes:
        G.nodes[node]['x'] = pos[node][0]
        G.nodes[node]['z'] = pos[node][1]
        
    # Add z coordiante from PageRank. Reverse arrows temporarily
    G_reversed = G.reverse()
    pr = nx.pagerank(G_reversed)
    for node in G.nodes:
        G.nodes[node]['y'] = pr[node]

    # Scale to y[0, 2] and x, z[-1, 1]
    y = nx.get_node_attributes(G, 'y')
    y_min, y_max = min(y.values()), max(y.values())
    x = nx.get_node_attributes(G, 'x')
    x_min, x_max = min(x.values()), max(x.values())
    z = nx.get_node_attributes(G, 'z')
    z_min, z_max = min(z.values()), max(z.values())
    for node in G.nodes:
        # normalize y with sqrt, but remove n
        corrected_y = max(0, y[node] - y_min)
        G.nodes[node]['y'] = 2 * sqrt(corrected_y / (y_max - y_min))
        G.nodes[node]['x'] = 2 * (x[node] - x_min) / (x_max - x_min) - 1
        G.nodes[node]['z'] = 2 * (z[node] - z_min) / (z_max - z_min) - 1

    return G
