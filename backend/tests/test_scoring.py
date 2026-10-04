"""Dallas–Atlanta detours around a Houston hurricane and keeps it when risk is zero."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.models import City, Hop
from app.routing.cities import city_id
from scoring import plan_routes

AS_OF = datetime(2026, 6, 15, tzinfo=UTC)
DEADLINE_HOURS = 72.0


def _city(name: str, state: str, lat: float, lon: float) -> City:
    return City(id=city_id(name, state), name=name, state=state, lat=lat, lon=lon)


def _hop(origin: City, dest: City, hours: float) -> Hop:
    return Hop(
        origin_id=origin.id,
        dest_id=dest.id,
        road_miles=hours * 55,
        drive_hours=hours,
    )


def _corridor() -> tuple[list[City], list[Hop]]:
    """Houston is the fast Dallas–Atlanta corridor. Little Rock is the long way around."""
    dallas = _city("Dallas", "TX", 32.7767, -96.7970)
    houston = _city("Houston", "TX", 29.7604, -95.3698)
    new_orleans = _city("New Orleans", "LA", 29.9511, -90.0715)
    atlanta = _city("Atlanta", "GA", 33.7490, -84.3880)
    little_rock = _city("Little Rock", "AR", 34.7465, -92.2896)
    memphis = _city("Memphis", "TN", 35.1495, -90.0490)
    cities = [dallas, houston, new_orleans, atlanta, little_rock, memphis]
    edges = [
        _hop(dallas, houston, 4),
        _hop(houston, new_orleans, 4),
        _hop(new_orleans, atlanta, 4),
        _hop(dallas, little_rock, 5),
        _hop(little_rock, memphis, 5),
        _hop(memphis, atlanta, 5),
    ]
    return cities, edges


def _names(route) -> list[str]:
    return [city.name for city in route.cities]


@pytest.fixture
def corridor_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def use(hazards: list[dict[str, object]]) -> None:
        hazard_path = tmp_path / "hazards.json"
        news_path = tmp_path / "news.json"
        hazard_path.write_text(json.dumps(hazards), encoding="utf-8")
        news_path.write_text("[]", encoding="utf-8")
        monkeypatch.setattr("hazards.MOCK_HAZARDS_PATH", hazard_path)
        monkeypatch.setattr("news.MOCK_NEWS_PATH", news_path)

    monkeypatch.setenv("USE_MOCK_DATA", "true")
    monkeypatch.setenv("NEWS_CACHE_PATH", str(tmp_path / "news.sqlite"))
    return use


def _hurricane() -> dict[str, object]:
    return {
        "event_id": "hou-hurricane",
        "event_type": "Hurricane",
        "event_name": "Hurricane near Houston",
        "lat": 29.7604,
        "lon": -95.3698,
        "date": "2026-06-15T00:00:00Z",
        "end_date": "2026-06-20T00:00:00Z",
        "city": "Houston",
        "state": "Texas",
        "country_code": "USA",
        "alert_level": "Red",
        "details": {},
    }


def test_hurricane_reroutes_dallas_atlanta_around_houston(corridor_files) -> None:
    corridor_files([_hurricane()])
    cities, edges = _corridor()
    plan = plan_routes(
        cities,
        edges,
        "Dallas, TX",
        "Atlanta, GA",
        as_of=AS_OF,
        deadline_hours=DEADLINE_HOURS,
    )
    assert _names(plan.baseline) == ["Dallas", "Houston", "New Orleans", "Atlanta"]
    best = plan.routes[0]
    assert "Houston" not in _names(best)
    assert best.avoided_cities == ["Houston", "New Orleans"]
    assert best.extra_drive_hours == pytest.approx(3)
    assert best.note == "This route avoids Houston, New Orleans and costs +3.0 hours."
    assert best.total_score < plan.baseline.total_score
    assert best.meets_deadline
    assert best.deadline_margin_hours > 0
    houston = next(item for item in plan.baseline.city_risks if item.name == "Houston")
    dallas = next(item for item in plan.baseline.city_risks if item.name == "Dallas")
    assert houston.hazard_risk == pytest.approx(1)
    assert any(factor.name == "hazard_risk" for factor in houston.factors)
    assert any(factor.event_id == "hou-hurricane" for factor in houston.factors)
    assert dallas.hazard_risk == pytest.approx(0)
    houston_edge = next(edge for edge in plan.baseline.edge_risks if edge.dest_id == "houston-tx" or edge.origin_id == "houston-tx")
    assert houston_edge.hazard_risk == pytest.approx(1)
    assert houston_edge.delay_hours == pytest.approx(8)


def test_zero_risk_dallas_atlanta_goes_through_houston(corridor_files) -> None:
    corridor_files([])
    cities, edges = _corridor()
    plan = plan_routes(
        cities,
        edges,
        "Dallas",
        "Atlanta",
        as_of=AS_OF,
        deadline_hours=DEADLINE_HOURS,
    )
    assert len(plan.routes) <= 3
    assert _names(plan.routes[0]) == ["Dallas", "Houston", "New Orleans", "Atlanta"]
    assert _names(plan.baseline) == _names(plan.routes[0])
    assert plan.routes[0].delay_hours_estimate == pytest.approx(0)
    assert plan.routes[0].news_risk_max == pytest.approx(0)
    assert plan.routes[0].hazard_risk_max == pytest.approx(0)
    assert plan.routes[0].note == "This route matches the baseline shortest path."
    assert plan.routes[0].total_hours == pytest.approx(plan.routes[0].drive_hours)
