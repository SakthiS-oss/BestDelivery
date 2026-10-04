"""Score candidate routes with hazard and news risk, then re-rank them.

Candidates are the fastest drive-time paths. Risk is applied only to the
cities and hops on those paths and the baseline, then the paths are ordered
by total score. A dangerous hop can lose to a longer safe hop that was
already a candidate. Delay is ``hazard_weight * hazard_risk + news_weight * news_risk``.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.models import City, Hop
from app.routing.candidates import k_shortest_routes, total_drive_hours
from app.routing.edges import edge_index
from app.scoring.deadline import estimate_itinerary
from hazards import hazard_risk_for_city, hazard_risk_for_edge
from news import news_risk_for_city, news_risks_for_cities

# Hours added when that risk score is 1. ``drive`` scales catalog drive hours.
DEFAULT_WEIGHTS: dict[str, float] = {
    "drive": 1.0,
    "hazard": 8.0,
    "news": 4.0,
}


class RiskFactor(BaseModel):
    """One named input copied from the hazard or news score."""

    name: str
    value: float
    unit: str = ""
    event_id: str | None = None


class CityRisk(BaseModel):
    """Hazard and news scores for one stop, with the factors behind them."""

    city_id: str
    name: str
    state: str
    hazard_risk: float
    news_risk: float
    factors: list[RiskFactor]
    events: list[str] = Field(default_factory=list)
    headlines: list[str] = Field(default_factory=list)


class EdgeRisk(BaseModel):
    """Risk and delay for one hop. ``delay_hours`` is the router's penalty."""

    origin_id: str
    dest_id: str
    drive_hours: float
    road_miles: float
    hazard_risk: float
    news_risk: float
    delay_hours: float
    factors: list[RiskFactor]
    events: list[str] = Field(default_factory=list)


class RouteResult(BaseModel):
    """One ordered route and the clock time used for its deadline check."""

    id: str
    cities: list[City]
    city_risks: list[CityRisk]
    edge_risks: list[EdgeRisk]
    drive_hours: float
    hazard_risk_max: float
    hazard_risk_avg: float
    news_risk_max: float
    news_risk_avg: float
    delay_hours_estimate: float
    total_hours: float
    total_score: float
    meets_deadline: bool
    deadline_margin_hours: float
    extra_drive_hours: float
    avoided_cities: list[str] = Field(default_factory=list)
    note: str


class RankedRoutes(BaseModel):
    """Baseline shortest path plus up to three routes chosen with risk penalties."""

    as_of: datetime
    deadline_hours: float
    weights: dict[str, float]
    baseline: RouteResult
    routes: list[RouteResult]


def delay_hours_for_risk(
    hazard_risk: float,
    news_risk: float,
    weights: dict[str, float] | None = None,
) -> float:
    """Hours a segment adds because of risk.

    ``delay = hazard_weight * hazard_risk + news_weight * news_risk``.
    Both scores are on 0–1. A hazard score of 1 adds ``weights["hazard"]``
    hours (default 8). A news score of 1 adds ``weights["news"]`` hours
    (default 4). A zero score adds no time.
    """
    chosen = _weights(weights)
    return chosen["hazard"] * hazard_risk + chosen["news"] * news_risk


def plan_routes(
    cities: list[City],
    edges: list[Hop],
    origin: str,
    destination: str,
    *,
    as_of: datetime,
    deadline_hours: float,
    k: int = 3,
    weights: dict[str, float] | None = None,
    hazard_lookback_days: float = 30.0,
    news_lookback_days: float = 7.0,
) -> RankedRoutes:
    """Return the risk-free baseline and the top risk-aware routes.

    ``total_hours`` is drive time plus delay, before overnight rest.
    The deadline uses that total plus the 10-hour driving day and 8-hour rest
    rule. ``deadline_margin_hours`` is spare time before the deadline; negative
    means the route is late.
    """
    chosen = _weights(weights)
    baseline_path = k_shortest_routes(cities, edges, origin, destination, k=1)[0]
    candidate_paths = k_shortest_routes(cities, edges, origin, destination, k=k)
    unique_cities: list[City] = []
    seen: set[str] = set()
    for path in (baseline_path, *candidate_paths):
        for city in path:
            if city.id not in seen:
                seen.add(city.id)
                unique_cities.append(city)
    news_by_city = news_risks_for_cities(unique_cities, as_of, news_lookback_days)
    context = _RiskContext(
        cities,
        edges,
        as_of,
        chosen,
        hazard_lookback_days,
        news_lookback_days,
        news_by_city,
    )
    baseline = context.score("baseline", baseline_path, deadline_hours)
    proposed = [context.score(f"route-{index}", path, deadline_hours) for index, path in enumerate(candidate_paths, start=1)]
    proposed.sort(key=lambda route: (route.total_score, route.drive_hours, route.id))
    for index, route in enumerate(proposed, start=1):
        route.id = f"route-{index}"
    _annotate(baseline, proposed)
    return RankedRoutes(
        as_of=as_of,
        deadline_hours=deadline_hours,
        weights=chosen,
        baseline=baseline,
        routes=proposed,
    )


class _RiskContext:
    """Cached city and edge scores for one ``as_of``."""

    def __init__(
        self,
        cities: list[City],
        edges: list[Hop],
        as_of: datetime,
        weights: dict[str, float],
        hazard_lookback_days: float,
        news_lookback_days: float,
        news_by_city: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.cities = {city.id: city for city in cities}
        self.hops = list(edges)
        self.edges = edge_index(edges)
        self.as_of = as_of
        self.weights = weights
        self.hazard_lookback_days = hazard_lookback_days
        self.news_lookback_days = news_lookback_days
        self.news_by_city = news_by_city or {}
        self._cities: dict[str, CityRisk] = {}
        self._edges: dict[tuple[str, str], EdgeRisk] = {}

    def penalty(self, origin_id: str, dest_id: str) -> float:
        """Risk penalty in hours for the edge-cost function."""
        return self.edge_risk(origin_id, dest_id).delay_hours

    def city_risk(self, city_id: str) -> CityRisk:
        cached = self._cities.get(city_id)
        if cached is not None:
            return cached
        city = self.cities[city_id]
        hazard = hazard_risk_for_city(city, self.as_of, self.hazard_lookback_days)
        news = self.news_by_city.get(city_id)
        if news is None:
            news = news_risk_for_city(city, self.as_of, self.news_lookback_days)
        record = CityRisk(
            city_id=city.id,
            name=city.name,
            state=city.state,
            hazard_risk=float(hazard["score"]),
            news_risk=float(news["score"]),
            factors=_factors(hazard["factors"]) + _factors(news["factors"]),
            events=_labels(hazard.get("events"), "event_name", "event_type"),
            headlines=_labels(news.get("articles"), "headline"),
        )
        self._cities[city_id] = record
        return record

    def edge_risk(self, origin_id: str, dest_id: str) -> EdgeRisk:
        key = (origin_id, dest_id)
        cached = self._edges.get(key) or self._edges.get((dest_id, origin_id))
        if cached is not None:
            return cached
        hop = self.edges.get(key)
        if hop is None:
            raise ValueError(f"no road hop from {origin_id} to {dest_id}")
        hazard = hazard_risk_for_edge(
            self.cities[origin_id],
            self.cities[dest_id],
            self.as_of,
            self.hazard_lookback_days,
        )
        origin_news = self.city_risk(origin_id).news_risk
        dest_news = self.city_risk(dest_id).news_risk
        news_risk = max(origin_news, dest_news)
        hazard_risk = float(hazard["score"])
        record = EdgeRisk(
            origin_id=hop.origin_id,
            dest_id=hop.dest_id,
            drive_hours=hop.drive_hours,
            road_miles=hop.road_miles,
            hazard_risk=hazard_risk,
            news_risk=news_risk,
            delay_hours=delay_hours_for_risk(hazard_risk, news_risk, self.weights),
            factors=_factors(hazard["factors"])
            + [RiskFactor(name="news_risk", value=news_risk, unit="0-1")],
            events=_labels(hazard.get("events"), "event_name", "event_type"),
        )
        self._edges[(hop.origin_id, hop.dest_id)] = record
        self._edges[(hop.dest_id, hop.origin_id)] = record
        return record

    def score(self, route_id: str, path: list[City], deadline_hours: float) -> RouteResult:
        city_risks = [self.city_risk(city.id) for city in path]
        edge_risks = [
            self.edge_risk(origin.id, dest.id) for origin, dest in zip(path, path[1:])
        ]
        drive = total_drive_hours(path, self.hops)
        delay = sum(edge.delay_hours for edge in edge_risks)
        hazard_values = [item.hazard_risk for item in city_risks] + [item.hazard_risk for item in edge_risks]
        news_values = [item.news_risk for item in city_risks] + [item.news_risk for item in edge_risks]
        total_hours = drive + delay
        elapsed = estimate_itinerary(total_hours, deadline_hours)
        return RouteResult(
            id=route_id,
            cities=list(path),
            city_risks=city_risks,
            edge_risks=edge_risks,
            drive_hours=drive,
            hazard_risk_max=_peak(hazard_values),
            hazard_risk_avg=_average(hazard_values),
            news_risk_max=_peak(news_values),
            news_risk_avg=_average(news_values),
            delay_hours_estimate=delay,
            total_hours=total_hours,
            total_score=self.weights["drive"] * drive + delay,
            meets_deadline=elapsed.meets_deadline,
            deadline_margin_hours=deadline_hours - elapsed.elapsed_hours,
            extra_drive_hours=0.0,
            note="",
        )


def _annotate(baseline: RouteResult, routes: list[RouteResult]) -> None:
    baseline.note = "Baseline shortest path, ignoring risk."
    baseline_ids = {city.id for city in baseline.cities}
    for route in routes:
        route.extra_drive_hours = route.drive_hours - baseline.drive_hours
        chosen = {city.id for city in route.cities}
        route.avoided_cities = [
            city.name
            for city in baseline.cities
            if city.id not in chosen and city.id not in {baseline.cities[0].id, baseline.cities[-1].id}
        ]
        if route.avoided_cities:
            names = ", ".join(route.avoided_cities)
            route.note = f"This route avoids {names} and costs {route.extra_drive_hours:+.1f} hours."
        elif {city.id for city in route.cities} == baseline_ids:
            route.note = "This route matches the baseline shortest path."
        else:
            route.note = f"This route costs {route.extra_drive_hours:+.1f} hours versus the baseline."


def _weights(overrides: dict[str, float] | None) -> dict[str, float]:
    chosen = dict(DEFAULT_WEIGHTS)
    if overrides:
        unknown = set(overrides) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"unknown weight: {', '.join(sorted(unknown))}")
        chosen.update(overrides)
    if chosen["drive"] < 0 or chosen["hazard"] < 0 or chosen["news"] < 0:
        raise ValueError("weights must be non-negative")
    return chosen


def _labels(raw: object, *keys: str) -> list[str]:
    """Copy the first present text field from each event or article."""
    if not isinstance(raw, list):
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = ""
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                label = value.strip()
                break
        if label and label.casefold() not in seen:
            seen.add(label.casefold())
            labels.append(label)
    return labels


def _factors(raw: object) -> list[RiskFactor]:
    if not isinstance(raw, list):
        return []
    factors: list[RiskFactor] = []
    for item in raw:
        if not isinstance(item, dict) or "value" not in item:
            continue
        event_id = item.get("event_id")
        factors.append(
            RiskFactor(
                name=str(item.get("name") or "factor"),
                value=float(item["value"]),
                unit=str(item.get("unit") or ""),
                event_id=str(event_id) if event_id else None,
            )
        )
    return factors


def _peak(values: list[float]) -> float:
    return max(values) if values else 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
