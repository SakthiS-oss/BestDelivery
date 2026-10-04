"""Undirected road graph with a caller-supplied risk penalty."""

import networkx as nx

from app.domain.models import Hop
from app.routing.cost import RiskPenalty, edge_cost, zero_risk_penalty


def build_cost_graph(
    edges: list[Hop],
    risk_penalty: RiskPenalty = zero_risk_penalty,
) -> nx.Graph:
    """Weight each hop as drive hours plus the penalty for that city pair."""
    graph = nx.Graph()
    for edge in edges:
        penalty = risk_penalty(edge.origin_id, edge.dest_id)
        graph.add_edge(
            edge.origin_id,
            edge.dest_id,
            weight=edge_cost(edge.drive_hours, penalty),
            drive_hours=edge.drive_hours,
            road_miles=edge.road_miles,
        )
    return graph
