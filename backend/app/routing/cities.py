"""Major-city catalog."""

from pathlib import Path

from app.domain.models import City


def load_cities(path: Path) -> list[City]:
    """Load cities from a CSV with columns id, name, state, lat, lon."""
    raise NotImplementedError


def resolve_city(cities: list[City], query: str) -> City:
    """Match a user-typed city string to one catalog row."""
    raise NotImplementedError
