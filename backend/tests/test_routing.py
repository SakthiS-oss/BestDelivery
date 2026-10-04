"""Routing engine: k shortest paths and overnight deadline checks."""

from pathlib import Path

import networkx as nx
import pytest

from app.routing.candidates import assess_route, k_shortest_routes, total_drive_hours
from app.routing.cities import load_cities
from app.routing.cost import edge_cost
from app.routing.edges import edge_index, load_edges
from app.routing.graph import build_cost_graph
from app.scoring.deadline import estimate_itinerary

ROOT = Path(__file__).resolve().parents[2]
CITIES = ROOT / "data" / "cities.csv"
EDGES = ROOT / "data" / "edges.csv"


@pytest.fixture(scope="module")
def network():
    cities = load_cities(CITIES)
    return cities, load_edges(EDGES, cities)


def _assert_hop_window(route, edges) -> None:
    index = edge_index(edges)
    for origin, dest in zip(route, route[1:]):
        hop = index[(origin.id, dest.id)]
        assert 100 <= hop.road_miles <= 400


def test_chicago_to_atlanta(network) -> None:
    cities, edges = network
    routes = k_shortest_routes(cities, edges, "Chicago, IL", "Atlanta, GA", k=3)
    assert len(routes) == 3
    assert len({tuple(city.id for city in route) for route in routes}) == 3
    drive = [total_drive_hours(route, edges) for route in routes]
    assert drive == sorted(drive)
    for route in routes:
        assert (route[0].name, route[0].state) == ("Chicago", "IL")
        assert (route[-1].name, route[-1].state) == ("Atlanta", "GA")
        assert len({city.id for city in route}) == len(route)
        _assert_hop_window(route, edges)
    estimate = assess_route(routes[0], edges, deadline_hours=24 * 5)
    assert estimate.meets_deadline
    assert estimate.elapsed_hours == pytest.approx(drive[0] + estimate.rest_hours)


def test_seattle_to_miami(network) -> None:
    cities, edges = network
    routes = k_shortest_routes(cities, edges, "Seattle", "Miami", k=3)
    assert len(routes) == 3
    assert len({tuple(city.id for city in route) for route in routes}) == 3
    drive = [total_drive_hours(route, edges) for route in routes]
    assert drive == sorted(drive)
    for route in routes:
        assert (route[0].name, route[0].state) == ("Seattle", "WA")
        assert (route[-1].name, route[-1].state) == ("Miami", "FL")
        _assert_hop_window(route, edges)
    estimate = assess_route(routes[0], edges, deadline_hours=24 * 14)
    assert estimate.overnight_stops >= 2
    assert estimate.elapsed_hours > drive[0]
    assert estimate.meets_deadline


def test_impossible_deadline(network) -> None:
    cities, edges = network
    routes = k_shortest_routes(cities, edges, "Seattle, WA", "Miami, FL", k=1)
    drive = total_drive_hours(routes[0], edges)
    estimate = assess_route(routes[0], edges, deadline_hours=1)
    assert estimate.drive_hours == pytest.approx(drive)
    assert estimate.overnight_stops >= 1
    assert estimate.rest_hours == estimate.overnight_stops * 8
    assert estimate.elapsed_hours > 1
    assert estimate.meets_deadline is False


def test_risk_penalty_replaces_the_fastest_first_hop(network) -> None:
    cities, edges = network
    baseline = k_shortest_routes(cities, edges, "Chicago", "Atlanta", k=1)[0]
    blocked = frozenset((baseline[0].id, baseline[1].id))

    def penalty(origin_id: str, dest_id: str) -> float:
        if frozenset((origin_id, dest_id)) == blocked:
            return 500.0
        return 0.0

    rerouted = k_shortest_routes(cities, edges, "Chicago", "Atlanta", k=1, risk_penalty=penalty)[0]
    assert frozenset((rerouted[0].id, rerouted[1].id)) != blocked
    assert edge_cost(5.0, 0.0) == 5.0
    assert edge_cost(5.0, 2.5) == 7.5


def test_catalog_graph_is_connected(network) -> None:
    cities, edges = network
    graph = build_cost_graph(edges)
    assert graph.number_of_nodes() == len(cities)
    assert nx.is_connected(graph)
    for _origin, _dest, data in graph.edges(data=True):
        assert 100 <= data["road_miles"] <= 400
        assert data["drive_hours"] == pytest.approx(data["road_miles"] / 55, abs=0.02)


def test_ten_hour_days_insert_eight_hour_rests() -> None:
    same_day = estimate_itinerary(10, deadline_hours=10)
    assert same_day.overnight_stops == 0
    assert same_day.elapsed_hours == pytest.approx(10)
    assert same_day.meets_deadline

    with_rest = estimate_itinerary(10.5, deadline_hours=18.5)
    assert with_rest.overnight_stops == 1
    assert with_rest.rest_hours == 8
    assert with_rest.elapsed_hours == pytest.approx(18.5)
    assert with_rest.meets_deadline

    missed = estimate_itinerary(10.5, deadline_hours=18)
    assert missed.meets_deadline is False
