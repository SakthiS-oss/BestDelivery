"""Catalog lookup and plan calls, with a fallback when a source is down."""

import math
import os
import threading
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

import hazards
import news
import scoring
from explain import explain_routes
from app.api.schemas import CityOption, CityRiskResponse, HealthResponse, PlanRequest, PlanResponse
from app.domain.models import City
from app.routing.cities import load_cities, resolve_city
from app.routing.edges import load_edges
from scoring import RankedRoutes, plan_routes
from snowflake_client import health_check, snowflake_session, use_mock_data

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUEST_TIMEOUT_SECONDS = 60.0
OLLAMA_PROBE_SECONDS = 2.0
HAZARD_WARNING = "Snowflake is unavailable; hazard scores were omitted."
NEWS_WARNING = "News data is unavailable; news scores were omitted."
OLLAMA_WARNING = "Ollama is unavailable; uncached news was left unclassified."


class CatalogError(RuntimeError):
    """The local city or road file cannot be used."""


_catalog: tuple[list[City], list] | None = None
_plan_lock = threading.Lock()
_CATALOG_HINT = "From the repo root, run: python scripts/seed_demo.py"


def request_timeout_seconds() -> float:
    """Seconds a single HTTP request may run before the server returns 504."""
    raw = os.environ.get("REQUEST_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return REQUEST_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return REQUEST_TIMEOUT_SECONDS
    if not math.isfinite(value) or value <= 0:
        return REQUEST_TIMEOUT_SECONDS
    return value


def load_catalog() -> tuple[list[City], list]:
    """Load the city list and road hops once per process."""
    global _catalog
    if _catalog is None:
        try:
            cities = load_cities(REPO_ROOT / "data" / "cities.csv")
            edges = load_edges(REPO_ROOT / "data" / "edges.csv", cities)
        except (OSError, ValueError) as exc:
            raise CatalogError(f"City catalog is unavailable. {_CATALOG_HINT}") from exc
        if not cities or not edges:
            raise CatalogError(f"The city catalog is empty. {_CATALOG_HINT}")
        _catalog = (cities, edges)
    return _catalog


def list_city_options() -> list[CityOption]:
    """Supported cities, sorted for an autocomplete menu."""
    cities, _edges = load_catalog()
    options = [_city_option(city) for city in cities]
    options.sort(key=lambda city: (city.name.lower(), city.state))
    return options


def build_health() -> HealthResponse:
    """Snowflake and Ollama probes. Mock mode reports both as skipped."""
    report = health_check()
    ollama = ollama_status()
    status = str(report["status"])
    if ollama == "unavailable":
        status = "degraded"
    return HealthResponse(
        status=status,
        use_mock_data=bool(report["use_mock_data"]),
        snowflake=str(report["snowflake"]),
        ollama=ollama,
    )


def ollama_status() -> str:
    """``skipped`` in mock mode, otherwise ``ok`` or ``unavailable``."""
    if use_mock_data():
        return "skipped"
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        response = httpx.get(f"{base}/api/tags", timeout=OLLAMA_PROBE_SECONDS)
        response.raise_for_status()
    except Exception:
        return "unavailable"
    return "ok"


def build_plan(request: PlanRequest) -> PlanResponse:
    """Resolve the request, rank routes, and keep going when a source is down."""
    as_of = resolve_as_of(request.as_of_date)
    deadline_hours = resolve_deadline_hours(request.deadline, as_of)
    cities, edges = load_catalog()
    start = resolve_city(cities, request.start)
    end = resolve_city(cities, request.end)
    warnings: list[str] = []
    ranked = rank_with_fallback(
        cities,
        edges,
        f"{start.name}, {start.state}",
        f"{end.name}, {end.state}",
        as_of,
        deadline_hours,
        warnings,
    )
    explained = explain_routes([ranked.baseline, *ranked.routes])
    if explained.source == "template" and not use_mock_data():
        _warn(
            warnings,
            "Explanation used the local template because the model output was not grounded.",
        )
    return PlanResponse(
        as_of=ranked.as_of,
        deadline_hours=ranked.deadline_hours,
        weights=ranked.weights,
        baseline=ranked.baseline,
        routes=ranked.routes,
        warnings=warnings,
        explanations=explained.routes,
        recommendation=explained.recommendation,
        explanation_source=explained.source,
    )


def build_city_risk(name: str, as_of_date: str | None) -> CityRiskResponse:
    """Hazard and news detail for one catalog city."""
    as_of = resolve_as_of(as_of_date)
    cities, _edges = load_catalog()
    city = resolve_city(cities, name)
    warnings: list[str] = []
    _note_ollama(warnings)
    hazard = _call_source(
        lambda: hazards.hazard_risk_for_city(city, as_of),
        _empty_hazard,
        HAZARD_WARNING,
        warnings,
    )
    article_news = _call_source(
        lambda: news.news_risk_for_city(city, as_of),
        _empty_news,
        NEWS_WARNING,
        warnings,
    )
    return CityRiskResponse(
        city=_city_option(city),
        as_of_date=as_of,
        hazard=hazard,
        news=article_news,
        warnings=warnings,
    )


def resolve_as_of(value: date | datetime | str | None) -> datetime:
    """Turn a missing value, a calendar date, or a timestamp into a UTC instant."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return datetime.now(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return _end_of_utc_day(value)
    text = value.strip()
    try:
        if "T" not in text and " " not in text:
            return _end_of_utc_day(date.fromisoformat(text))
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("as_of_date must be an ISO-8601 date or datetime") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def resolve_deadline_hours(deadline: float | datetime, as_of: datetime) -> float:
    """Hours from as_of until the deadline."""
    if isinstance(deadline, datetime):
        moment = deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)
        hours = (moment.astimezone(UTC) - as_of).total_seconds() / 3600
    else:
        hours = float(deadline)
    if not math.isfinite(hours) or hours <= 0:
        raise ValueError("deadline must be a positive number of hours, or a timestamp after as_of_date")
    return hours


def rank_with_fallback(
    cities: list[City],
    edges: list,
    origin: str,
    destination: str,
    as_of: datetime,
    deadline_hours: float,
    warnings: list[str],
) -> RankedRoutes:
    """Call the ranker. A down Snowflake or Ollama becomes a warning and a zero score."""
    _note_ollama(warnings)

    def hazard_city(city: object, as_of_date: date | datetime, lookback_days: float = 30.0) -> dict[str, object]:
        return _call_source(
            lambda: hazards.hazard_risk_for_city(city, as_of_date, lookback_days),
            _empty_hazard,
            HAZARD_WARNING,
            warnings,
        )

    def hazard_edge(
        origin_city: object,
        destination_city: object,
        as_of_date: date | datetime,
        lookback_days: float = 30.0,
    ) -> dict[str, object]:
        return _call_source(
            lambda: hazards.hazard_risk_for_edge(origin_city, destination_city, as_of_date, lookback_days),
            _empty_hazard,
            HAZARD_WARNING,
            warnings,
        )

    def news_city(city: object, as_of_date: date | datetime, lookback_days: float | None = None) -> dict[str, object]:
        return _call_source(
            lambda: news.news_risk_for_city(city, as_of_date, lookback_days),
            _empty_news,
            NEWS_WARNING,
            warnings,
        )

    def news_batch(
        batch: list[object],
        as_of_date: date | datetime,
        lookback_days: float | None = None,
    ) -> dict[str, object]:
        return _call_source(
            lambda: news.news_risks_for_cities(batch, as_of_date, lookback_days),
            lambda: {_plan_city_key(city): _empty_news() for city in batch},
            NEWS_WARNING,
            warnings,
        )

    def run_plan() -> RankedRoutes:
        return plan_routes(
            cities,
            edges,
            origin,
            destination,
            as_of=as_of,
            deadline_hours=deadline_hours,
        )

    with _plan_lock:
        previous = (
            scoring.hazard_risk_for_city,
            scoring.hazard_risk_for_edge,
            scoring.news_risk_for_city,
            scoring.news_risks_for_cities,
        )
        scoring.hazard_risk_for_city = hazard_city
        scoring.hazard_risk_for_edge = hazard_edge
        scoring.news_risk_for_city = news_city
        scoring.news_risks_for_cities = news_batch
        try:
            if use_mock_data():
                return run_plan()
            try:
                with snowflake_session():
                    return run_plan()
            except Exception as exc:
                if not is_dependency_failure(exc):
                    raise
                _warn(warnings, HAZARD_WARNING)
                _warn(warnings, NEWS_WARNING)
                scoring.hazard_risk_for_city = lambda *_args, **_kwargs: _empty_hazard()
                scoring.hazard_risk_for_edge = lambda *_args, **_kwargs: _empty_hazard()
                scoring.news_risks_for_cities = lambda batch, *_args, **_kwargs: {
                    _plan_city_key(city): _empty_news() for city in batch
                }
                return run_plan()
        finally:
            (
                scoring.hazard_risk_for_city,
                scoring.hazard_risk_for_edge,
                scoring.news_risk_for_city,
                scoring.news_risks_for_cities,
            ) = previous


def is_dependency_failure(exc: BaseException) -> bool:
    """True when Snowflake, Ollama, or the network failed. Local bugs stay errors."""
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.HTTPError)):
        return True
    if isinstance(exc, OSError) and not isinstance(exc, (FileNotFoundError, PermissionError, IsADirectoryError)):
        return True
    if type(exc).__module__.startswith("snowflake"):
        return True
    return isinstance(exc, RuntimeError) and "Snowflake" in str(exc)


def _call_source(load, empty, warning: str, warnings: list[str]) -> dict[str, object]:
    try:
        result = load()
    except Exception as exc:
        if not is_dependency_failure(exc):
            raise
        _warn(warnings, warning)
        return empty()
    if not isinstance(result, dict):
        raise TypeError("source score must be a dict")
    return result


def _note_ollama(warnings: list[str]) -> None:
    if not use_mock_data() and ollama_status() == "unavailable":
        _warn(warnings, OLLAMA_WARNING)


def _warn(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def _city_option(city: City) -> CityOption:
    return CityOption(
        id=city.id,
        name=city.name,
        state=city.state,
        label=f"{city.name}, {city.state}",
        lat=city.lat,
        lon=city.lon,
    )


def _end_of_utc_day(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=UTC)


def _plan_city_key(city: object) -> str:
    if isinstance(city, dict) and city.get("id"):
        return str(city["id"])
    city_id = getattr(city, "id", None)
    if city_id:
        return str(city_id)
    return str(getattr(city, "name", "")).casefold()


def _empty_hazard() -> dict[str, object]:
    return {"score": 0.0, "factors": [], "events": []}


def _empty_news() -> dict[str, object]:
    return {
        "score": 0.0,
        "factors": [
            {"name": "matched_articles", "value": 0, "unit": "articles"},
            {"name": "road_affecting_articles", "value": 0, "unit": "articles"},
            {"name": "prior_road_affecting_articles", "value": 0, "unit": "articles"},
            {"name": "news_risk", "value": 0.0, "unit": "0-1"},
        ],
        "articles": [],
        "trend": {"direction": "flat", "current_road_events": 0, "prior_road_events": 0},
    }
