import networkx as nx
import json

# Load the extracted_nodes.json data
with open('extracted_nodes.json') as f:
    nodes_data = json.load(f)

# Create a new directed graph
G = nx.DiGraph()

# Create nodes for all entities
for node in nodes_data:
    G.add_node(node['entity'])

# Create edges between entities that appear in the same FIR
for node in nodes_data:
    for other_node in nodes_data:
        if node['FIR'] == other_node['FIR']:
            G.add_edge(node['entity'], other_node['entity'])

# Calculate PageRank scores
pr = nx.pagerank(G)

# Calculate Betweenness Centrality scores
bc = nx.betweenness_centrality(G)

# Attach scores as node attributes
for node, score in pr.items():
    G.nodes[node]['PageRank'] = score
for node, score in bc.items():
    G.nodes[node]['Betweenness Centrality'] = score

# Export the graph to a new JSON file
with open('graph.json', 'w') as f:
    json.dump(json_graph.node_link_data(G), f)

print("Graph exported to graph.json")