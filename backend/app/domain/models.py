"""Shared records. Fields only; calculations live in other modules."""

from pydantic import BaseModel


class City(BaseModel):
    """A major US city a truck can stop and refuel in."""

    id: str
    name: str
    state: str
    lat: float
    lon: float
    population: int = 0


class Hop(BaseModel):
    """One drive between two catalog cities."""

    origin_id: str
    dest_id: str
    road_miles: float
    drive_hours: float
