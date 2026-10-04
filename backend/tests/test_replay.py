"""as_of cuts off later hazards and news, including inside a scored plan."""

import json
from datetime import UTC, datetime

import pytest

from app.domain.models import City, Hop
from app.routing.cities import city_id
from backtest import route_avoided
from hazards import _events_sql, get_hazard_events, hazard_risk_for_city
from news import get_news_for_city, news_match_sql, news_risk_for_city
from scoring import plan_routes

AS_OF = datetime(2026, 6, 15, tzinfo=UTC)
HOUSTON = {"name": "Houston", "state": "TX", "lat": 29.7604, "lon": -95.3698}


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("USE_MOCK_DATA", "true")
    monkeypatch.setenv("NEWS_CACHE_PATH", str(tmp_path / "news.sqlite"))
    hazard_path = tmp_path / "hazards.json"
    news_path = tmp_path / "news.json"
    monkeypatch.setattr("hazards.MOCK_HAZARDS_PATH", hazard_path)
    monkeypatch.setattr("news.MOCK_NEWS_PATH", news_path)
    return hazard_path, news_path


def test_sql_keeps_only_rows_dated_on_or_before_as_of() -> None:
    hazard_sql = _events_sql("ND.ND_ACTUALS", by_state=False)
    news_sql = news_match_sql("NEWS.BBC_NEWS", include_state=False)
    assert "start_ts <= %(as_of)s" in hazard_sql
    assert "published_at <= %(as_of)s" in news_sql
    assert "published_at > %(window_start)s" in news_sql


def test_future_records_do_not_change_city_or_route_scores(isolated) -> None:
    hazard_path, news_path = isolated
    past_only = [_hazard("past-flood", "2026-06-10T00:00:00Z"), _news("past-news", "2026-06-14T12:00:00Z")]
    with_future = [
        past_only[0],
        _hazard("future-flood", "2026-06-18T00:00:00Z"),
        past_only[1],
        _news("future-news", "2026-06-16T12:00:00Z"),
    ]
    _write(hazard_path, news_path, [with_future[0], with_future[1]], [with_future[2], with_future[3]])

    events = get_hazard_events((29.0, -96.2, 30.4, -94.8), AS_OF, 30)
    assert {event["event_id"] for event in events} == {"past-flood"}
    assert all(event["start_time"] <= AS_OF for event in events)

    articles = get_news_for_city(HOUSTON, AS_OF, 7)
    assert {article["id"] for article in articles} == {"past-news"}
    assert all(datetime.fromisoformat(str(article["date"])) <= AS_OF for article in articles)

    leaked_hazard = hazard_risk_for_city(HOUSTON, AS_OF, lookback_days=30)
    leaked_news = news_risk_for_city(HOUSTON, AS_OF, lookback_days=7)
    assert "future-flood" not in {event["event_id"] for event in leaked_hazard["events"]}
    assert "future-news" not in {article["id"] for article in leaked_news["articles"]}

    _write(hazard_path, news_path, [past_only[0]], [past_only[1]])
    past_hazard = hazard_risk_for_city(HOUSTON, AS_OF, lookback_days=30)
    past_news = news_risk_for_city(HOUSTON, AS_OF, lookback_days=7)
    assert leaked_hazard["score"] == pytest.approx(past_hazard["score"])
    assert leaked_news["score"] == pytest.approx(past_news["score"])

    _write(hazard_path, news_path, [with_future[0], with_future[1]], [with_future[2], with_future[3]])
    plan = plan_routes(_cities(), _edges(), "Dallas, TX", "Atlanta, GA", as_of=AS_OF, deadline_hours=72)
    evidence = {
        factor.event_id
        for route in (plan.baseline, *plan.routes)
        for stop in route.city_risks
        for factor in stop.factors
    }
    assert "future-flood" not in evidence
    assert "past-flood" in evidence


def test_moving_as_of_forward_is_what_reveals_the_later_record(isolated) -> None:
    hazard_path, news_path = isolated
    _write(
        hazard_path,
        news_path,
        [_hazard("future-flood", "2026-06-18T00:00:00Z")],
        [_news("future-news", "2026-06-16T12:00:00Z")],
    )
    hidden = hazard_risk_for_city(HOUSTON, AS_OF, lookback_days=30)
    shown = hazard_risk_for_city(HOUSTON, datetime(2026, 6, 18, tzinfo=UTC), lookback_days=30)
    assert hidden["events"] == []
    assert {event["event_id"] for event in shown["events"]} == {"future-flood"}
    hidden_news = get_news_for_city(HOUSTON, AS_OF, 7)
    shown_news = get_news_for_city(HOUSTON, datetime(2026, 6, 16, 12, tzinfo=UTC), 7)
    assert hidden_news == []
    assert {article["id"] for article in shown_news} == {"future-news"}


def test_backtest_endpoint_reads_the_saved_report(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr("backtest.REPORT_PATH", tmp_path / "missing.json")
    missing = TestClient(app).get("/backtest")
    assert missing.status_code == 404
    assert "scripts/backtest.py" in missing.json()["detail"]

    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "disclaimer": "Historical replay only.",
                "events_tested": 1,
                "routes_through_danger": 2,
                "routes_avoided": 1,
                "average_extra_hours": 1.5,
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("backtest.REPORT_PATH", report)
    found = TestClient(app).get("/backtest")
    assert found.status_code == 200
    assert found.json()["routes_avoided"] == 1


def test_route_avoided_requires_the_baseline_to_have_entered_the_city() -> None:
    affected = {"houston-tx"}
    assert route_avoided(["dallas-tx", "houston-tx", "atlanta-ga"], ["dallas-tx", "little-rock-ar", "atlanta-ga"], affected)
    assert not route_avoided(
        ["dallas-tx", "houston-tx", "atlanta-ga"],
        ["dallas-tx", "houston-tx", "atlanta-ga"],
        affected,
    )
    assert not route_avoided(["dallas-tx", "atlanta-ga"], ["dallas-tx", "memphis-tn", "atlanta-ga"], affected)


def _hazard(event_id: str, when: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "Flood",
        "event_name": event_id,
        "lat": 29.7604,
        "lon": -95.3698,
        "date": when,
        "end_date": "2026-06-21T00:00:00Z",
        "city": "Houston",
        "state": "Texas",
        "country_code": "USA",
        "alert_level": "Red",
        "details": {},
    }


def _news(article_id: str, when: str) -> dict[str, object]:
    return {
        "id": article_id,
        "headline": "Houston freeway closure",
        "publication_date": when,
        "content": "Lanes are closed in Houston.",
        "classification": {
            "relevant": True,
            "event_type": "road_closure",
            "severity": 3,
            "affects_road_travel": True,
        },
    }


def _write(hazard_path, news_path, hazards: list[dict[str, object]], articles: list[dict[str, object]]) -> None:
    hazard_path.write_text(json.dumps(hazards), encoding="utf-8")
    news_path.write_text(json.dumps(articles), encoding="utf-8")


def _city(name: str, state: str, lat: float, lon: float) -> City:
    return City(id=city_id(name, state), name=name, state=state, lat=lat, lon=lon)


def _cities() -> list[City]:
    return [
        _city("Dallas", "TX", 32.7767, -96.7970),
        _city("Houston", "TX", 29.7604, -95.3698),
        _city("New Orleans", "LA", 29.9511, -90.0715),
        _city("Atlanta", "GA", 33.7490, -84.3880),
        _city("Little Rock", "AR", 34.7465, -92.2896),
        _city("Memphis", "TN", 35.1495, -90.0490),
    ]


def _edges() -> list[Hop]:
    cities = {city.name: city for city in _cities()}

    def hop(origin: str, dest: str, hours: float) -> Hop:
        return Hop(
            origin_id=cities[origin].id,
            dest_id=cities[dest].id,
            road_miles=hours * 55,
            drive_hours=hours,
        )

    return [
        hop("Dallas", "Houston", 4),
        hop("Houston", "New Orleans", 4),
        hop("New Orleans", "Atlanta", 4),
        hop("Dallas", "Little Rock", 5),
        hop("Little Rock", "Memphis", 5),
        hop("Memphis", "Atlanta", 5),
    ]
