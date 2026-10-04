"""Road hops stored in the edge catalog."""

import csv
from pathlib import Path

from app.domain.models import City, Hop
from app.routing.cities import city_id


def load_edges(path: Path, cities: list[City]) -> list[Hop]:
    """Load undirected road hops keyed by the city catalog."""
    known = {city.id for city in cities}
    edges: list[Hop] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            origin = city_id(row["from_city"].strip(), row["from_state"].strip())
            dest = city_id(row["to_city"].strip(), row["to_state"].strip())
            if origin not in known or dest not in known:
                raise ValueError(f"edge references an unknown city: {origin} -> {dest}")
            edges.append(
                Hop(
                    origin_id=origin,
                    dest_id=dest,
                    road_miles=float(row["road_miles"]),
                    drive_hours=float(row["typical_drive_hours"]),
                )
            )
    return edges


def edge_index(edges: list[Hop]) -> dict[tuple[str, str], Hop]:
    """Map both directions of each hop to the same record."""
    index: dict[tuple[str, str], Hop] = {}
    for edge in edges:
        index[(edge.origin_id, edge.dest_id)] = edge
        index[(edge.dest_id, edge.origin_id)] = edge
    return index
