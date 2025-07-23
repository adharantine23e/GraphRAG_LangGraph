import matplotlib.pyplot as plt
import matplotlib.cm as cm
from neo4j import GraphDatabase
import networkx as nx
import os
from typing import List, Dict, Any, Optional
import numpy as np
from dotenv import load_dotenv

load_dotenv(override=True)

class Visualization:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv["NEO4J_URI"],
            auth=(os.getenv["NEO4J_USERNAME"], os.getenv["NEO4J_PASSWORD"])
        )
        self.query = None
        self.graph = None
        self.nodes = None
        self.edges = None
        self.id_to_names = None

    def execute_query(self, query: str):
        with self.driver.session() as session:
            result = session.run(query)
            return result.graph()

    def show_general_graph(self, query: str, save_path: Optional[str], shown: bool = False):
        graph_data = self.execute_query(query=query)
        self.query = query
        G = nx.MultiDiGraph()
        nodes = list(graph_data._nodes.values())
        edges = list(graph_data._relationships.values())
        
        # Store nodes and edges
        self.nodes = nodes
        self.edges = edges
        self.id_to_names = {node.id: node._properties.get('id', node.id) for node in nodes}
        
        for node in nodes:
            G.add_node(node.id, labels=node._labels, properties=node._properties)
        for edge in edges:
            G.add_edge(edge.start_node.id, edge.end_node.id, key=edge.id, type=edge.type, properties=edge._properties)
        
        # Store grpah
        self.graph = G
        
        if shown:
            plt.figure(figsize=(12, 8))
            pos = nx.spring_layout(G, k=1, iterations=50, seed=69)
            nx.draw_networkx_nodes(G, pos, node_color='lightblue', node_size=1000, alpha=0.7)
            nx.draw_networkx_edges(G, pos, edge_color="gray", alpha=0.5, arrows=True, arrowstyle="->", width=1.5)

            # Truncate labels
            nodes_label = nx.get_node_attributes(G, "labels")
            nodes_label = {k: (','.join(v)[:15] + '...' if len(','.join(v)) > 15 else ','.join(v)) for k, v in nodes_label.items()}
            nx.draw_networkx_labels(G, pos, nodes_label, font_size=10, font_color="black")

            edges_label = nx.get_edge_attributes(G, 'type')  # Use 'type' for edge labels
            nx.draw_networkx_edge_labels(G, pos, edges_label, font_size=8)
            plt.title(f"Neo4j Graph Visualization ({len(G.nodes)} nodes, {len(G.edges)} edges)")
            plt.axis('off')
            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                print(f"Graph saved to {save_path}")
            plt.show()

        

    def degree_centrality(self):
        self.show_general_graph(query = self.query, save_path=None, shown=False)
        degree_centrality = nx.degree_centrality(self.graph)
        degree_centrality_named = {self.id_to_names[node_id]: centrality for node_id, centrality in degree_centrality.items()}

        # Just show 20 most degree centrality nodes
        top_20_centrality_named = dict(sorted(degree_centrality_named.items(), key=lambda item: item[1], reverse=True)[:20])
        top_20_centrality = dict(sorted(degree_centrality.items(), key=lambda item: item[1], reverse=True)[:20])
        # Extract names and centrality values
        names = list(top_20_centrality_named.keys())
        centrality_values = list(top_20_centrality_named.values())

        # Create bar charts
        plt.figure(figsize=(12, 8))
        plt.barh(names, centrality_values, color='skyblue')
        plt.xlabel('Degree Centrality')
        plt.ylabel('Node Names')
        plt.title('Top 20 Most Centralized Nodes')
        plt.gca().invert_yaxis()  # Invert y-axis to have the highest centrality at the top
        plt.show()
    
    def betweenness_centrality(self):
        self.show_general_graph(query = self.query, save_path=None, shown=False)
        betweenness_centrality = nx.betweenness_centrality(self.graph)
        betweenness_centrality_named = {self.id_to_names[node_id]: centrality for node_id, centrality in betweenness_centrality.items()}
        top_20_betweenness_centrality_named = dict(sorted(betweenness_centrality_named.items(), key=lambda item: item[1], reverse=True)[:20])
        # Extract names and centrality values
        names = list(top_20_betweenness_centrality_named.keys())
        centrality_values = list(top_20_betweenness_centrality_named.values())
        colors = cm.viridis(np.linspace(0, 1, len(names)))

        # Create a bar chart
        plt.figure(figsize=(12, 8))
        bars = plt.barh(names, centrality_values, color=colors)
        plt.xlabel('Degree Centrality')
        plt.ylabel('Node Names')
        plt.title('Top 20 Most Centralized Nodes')
        plt.gca().invert_yaxis()  # Invert y-axis to have the highest centrality at the top
        for bar, color in zip(bars, colors):
            bar.set_color(color)
        plt.show()

    def closeness_centrality(self):
        self.show_general_graph(query = self.query, save_path=None, shown=False)
        closeness_centrality = nx.closeness_centrality(self.graph)
        closeness_centrality_named = {self.id_to_names[node_id]: centrality for node_id, centrality in closeness_centrality.items()}
        top_20_closeness_centrality = dict(sorted(closeness_centrality_named.items(), key=lambda item: item[1], reverse=True)[:20])

        # Extract names and centrality values
        names = list(top_20_closeness_centrality.keys())
        centrality_values = list(top_20_closeness_centrality.values())
        colors = cm.viridis(np.linspace(0, 1, len(names)))

        # Create a bar chart
        plt.figure(figsize=(12, 8))
        bars = plt.barh(names, centrality_values, color=colors)
        plt.xlabel('Degree Centrality')
        plt.ylabel('Node Names')
        plt.title('Top 20 Most Centralized Nodes')
        plt.gca().invert_yaxis()  # Invert y-axis to have the highest centrality at the top
        for bar, color in zip(bars, colors):
            bar.set_color(color)
        plt.show()
