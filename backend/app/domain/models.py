"""Shared records. Fields only; calculations live in other modules."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FactorName = Literal[
    "hazard_risk",
    "news_risk",
    "delay_hours",
    "travel_hours",
    "deadline_slack_hours",
]


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


class Route(BaseModel):
    """An ordered city sequence and the driving totals computed for it."""

    id: str
    city_ids: list[str]
    hops: list[Hop]
    total_miles: float
    travel_hours: float


class DisasterEvent(BaseModel):
    """A natural-hazard record known at a point in time."""

    event_id: str
    event_type: str
    severity: float
    lat: float
    lon: float
    start_time: datetime
    end_time: datetime | None
    state: str
    summary: str


class NewsItem(BaseModel):
    """A news record published at or before as_of."""

    article_id: str
    published_at: datetime
    title: str
    summary: str
    city: str
    state: str
    tags: list[str]
    severity: float


class Factor(BaseModel):
    """One named term in a route score, with the record ids behind it."""

    name: FactorName
    value: float
    unit: str
    evidence_ids: list[str] = Field(default_factory=list)


class RouteScore(BaseModel):
    """Code-computed cost, deadline check, and factor breakdown."""

    factors: list[Factor]
    travel_cost_hours: float
    risk_cost_hours: float
    total_cost_hours: float
    eta: datetime
    meets_deadline: bool


class Citation(BaseModel):
    """A value the explanation is allowed to mention."""

    source: Literal["distance", "disaster", "news", "score"]
    record_id: str
    field: str
    value: str


class RouteResult(BaseModel):
    """A candidate route and its score, before any prose."""

    route: Route
    score: RouteScore


class ExplainedRoute(BaseModel):
    """A scored route plus prose that cites only these fields."""

    route: Route
    score: RouteScore
    explanation: str
    citations: list[Citation]
