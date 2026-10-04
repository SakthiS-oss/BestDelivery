"""Major-city catalog."""

import csv
from pathlib import Path

from app.domain.models import City


def city_id(name: str, state: str) -> str:
    """Stable id from a city name and state abbreviation."""
    raw = f"{name}-{state}".lower()
    return "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")


def load_cities(path: Path) -> list[City]:
    """Load cities from CSV columns name, state, lat, lon, and optional population."""
    cities: list[City] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = row["name"].strip()
            state = row["state"].strip()
            population = int(row["population"]) if row.get("population") else 0
            cities.append(
                City(
                    id=row["id"].strip() if row.get("id") else city_id(name, state),
                    name=name,
                    state=state,
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    population=population,
                )
            )
    return cities


def resolve_city(cities: list[City], query: str) -> City:
    """Match a user-typed city string to one catalog row."""
    text = " ".join(query.strip().split())
    if not text:
        raise ValueError("city query is empty")

    if "," in text:
        name_part, state_part = (part.strip() for part in text.split(",", 1))
        matches = [
            city
            for city in cities
            if city.name.lower() == name_part.lower() and city.state.lower() == state_part.lower()
        ]
    else:
        matches = [city for city in cities if city.name.lower() == text.lower()]

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"unknown city: {query}")
    names = ", ".join(f"{city.name}, {city.state}" for city in matches)
    raise ValueError(f"ambiguous city: {query} ({names})")
