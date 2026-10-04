"""Diverse paths through the hop graph."""

from datetime import datetime

from app.domain.models import City, Route
from app.routing.graph import Adjacency


def generate_routes(
    cities: list[City],
    graph: Adjacency,
    start: City,
    end: City,
    *,
    as_of: datetime,
    avg_speed_mph: float,
    count: int,
) -> list[Route]:
    """Return up to `count` city sequences from start to end for this as_of."""
    raise NotImplementedError
