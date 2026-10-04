"""Hop graph: edges exist only inside the refuel window."""

from app.domain.models import City

Adjacency = dict[str, list[tuple[str, float]]]


def build_graph(
    cities: list[City],
    *,
    min_hop_miles: float,
    max_hop_miles: float,
    road_factor: float,
) -> Adjacency:
    """Link city pairs whose estimated road miles fall inside the hop window."""
    raise NotImplementedError
