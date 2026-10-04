"""K shortest city sequences. Costs use drive time plus an optional risk penalty."""

import networkx as nx

from app.domain.models import City, Hop
from app.routing.cities import resolve_city
from app.routing.cost import RiskPenalty, zero_risk_penalty
from app.routing.edges import edge_index
from app.routing.graph import build_cost_graph
from app.scoring.deadline import ItineraryEstimate, estimate_itinerary


def k_shortest_routes(
    cities: list[City],
    edges: list[Hop],
    origin: str,
    destination: str,
    *,
    k: int = 3,
    risk_penalty: RiskPenalty = zero_risk_penalty,
) -> list[list[City]]:
    """Return up to k distinct simple paths, lowest edge cost first."""
    if k < 1:
        raise ValueError("k must be at least 1")
    start = resolve_city(cities, origin)
    end = resolve_city(cities, destination)
    by_id = {city.id: city for city in cities}
    graph = build_cost_graph(edges, risk_penalty)
    if start.id not in graph or end.id not in graph or not nx.has_path(graph, start.id, end.id):
        raise ValueError(f"no road path from {start.name}, {start.state} to {end.name}, {end.state}")

    routes: list[list[City]] = []
    seen: set[tuple[str, ...]] = set()
    for node_ids in nx.shortest_simple_paths(graph, start.id, end.id, weight="weight"):
        key = tuple(node_ids)
        if key in seen:
            continue
        seen.add(key)
        routes.append([by_id[node_id] for node_id in node_ids])
        if len(routes) == k:
            break
    return routes


def assess_route(
    route: list[City],
    edges: list[Hop],
    deadline_hours: float,
    *,
    max_drive_hours_per_day: float = 10.0,
    rest_hours_per_stop: float = 8.0,
) -> ItineraryEstimate:
    """Sum drive hours, add overnight rest, and compare the total with a deadline."""
    return estimate_itinerary(
        total_drive_hours(route, edges),
        deadline_hours,
        max_drive_hours_per_day=max_drive_hours_per_day,
        rest_hours_per_stop=rest_hours_per_stop,
    )


def total_drive_hours(route: list[City], edges: list[Hop]) -> float:
    """Sum catalog drive hours along an ordered city list."""
    index = edge_index(edges)
    total = 0.0
    for origin, dest in zip(route, route[1:]):
        hop = index.get((origin.id, dest.id))
        if hop is None:
            raise ValueError(f"no road hop from {origin.name} to {dest.name}")
        total += hop.drive_hours
    return total
