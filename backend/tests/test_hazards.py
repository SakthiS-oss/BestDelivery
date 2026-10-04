"""Mock-data tests for the Snowflake hazard layer."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from hazards import (
    hazard_risk_for_city,
    hazard_risk_for_edge,
    get_hazard_events,
    load_mock_hazards,
)
from snowflake_client import assert_select_only, health_check, qualified_table

AS_OF = datetime(2026, 6, 15, tzinfo=UTC)
CHICAGO = {"name": "Chicago", "lat": 41.8781, "lon": -87.6298}
WEST = {"name": "West", "lat": 40.0, "lon": -100.0}
EAST = {"name": "East", "lat": 40.0, "lon": -98.0}


@pytest.fixture(autouse=True)
def force_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_DATA", "true")


def test_select_only_rejects_writes() -> None:
    assert_select_only("SELECT 1 AS ok")
    assert_select_only("WITH rows AS (SELECT 1 AS n) SELECT n FROM rows")
    for sql in ("DELETE FROM t", "INSERT INTO t VALUES (1)", "UPDATE t SET a = 1", "SELECT 1; SELECT 2"):
        with pytest.raises(ValueError):
            assert_select_only(sql)


def test_table_name_is_checked() -> None:
    assert qualified_table(
        "AMBEE_GLOBAL_NATURAL_DISASTERS_DATA_HISTORICAL_AND_PRESENT_CONDITIONS.ND.ND_ACTUALS"
    ).endswith(".ND.ND_ACTUALS")
    with pytest.raises(ValueError):
        qualified_table("ND.ND_ACTUALS; DROP TABLE ND_ACTUALS")


def test_bbox_keeps_chicago_window_and_drops_old_and_distant() -> None:
    events = get_hazard_events((41.5, -88.2, 42.2, -87.2), AS_OF, 30)
    ids = {event["event_id"] for event in events}
    assert ids == {"chi-flood", "chi-storm"}


def test_state_name_and_ongoing_event_that_started_before_the_window() -> None:
    illinois = {event["event_id"] for event in get_hazard_events("Illinois", AS_OF, 30)}
    assert illinois == {"chi-flood", "chi-storm"}
    california = {event["event_id"] for event in get_hazard_events("california", AS_OF, 30)}
    assert "sf-beach" in california
    assert "sf-ongoing" in california


def test_city_score_uses_nearby_recent_events_only() -> None:
    result = hazard_risk_for_city(CHICAGO, AS_OF, lookback_days=30)
    ids = [event["event_id"] for event in result["events"]]
    assert ids[0] == "chi-flood"
    assert "chi-storm" in ids
    assert "chi-old" not in ids
    assert "chi-far" not in ids
    total = sum(float(event["contribution"]) for event in result["events"])
    assert result["score"] == pytest.approx(min(1.0, total))
    assert 0 < float(result["score"]) <= 1
    flood = next(event for event in result["events"] if event["event_id"] == "chi-flood")
    storm = next(event for event in result["events"] if event["event_id"] == "chi-storm")
    assert flood["contribution"] > storm["contribution"]
    assert any(factor["name"] == "hazard_risk" for factor in result["factors"])


def test_city_with_no_events_scores_zero() -> None:
    result = hazard_risk_for_city({"name": "Nowhere", "lat": 0.0, "lon": 0.0}, AS_OF)
    assert result["score"] == 0
    assert result["events"] == []


def test_edge_score_is_the_max_sample() -> None:
    edge = hazard_risk_for_edge(WEST, EAST, AS_OF, lookback_days=30)
    sample_scores = [float(sample["score"]) for sample in edge["samples"]]
    assert edge["aggregation"] == "max"
    assert edge["score"] == pytest.approx(max(sample_scores))
    assert float(edge["score"]) > float(hazard_risk_for_city(WEST, AS_OF)["score"])
    assert float(edge["score"]) > float(hazard_risk_for_city(EAST, AS_OF)["score"])
    assert any(event["event_id"] == "seg-red" for event in edge["events"])


def test_mock_queries_do_not_open_snowflake(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("Snowflake should not be queried in mock mode")

    monkeypatch.setattr("hazards.fetch_all", boom)
    assert len(load_mock_hazards()) >= 20
    assert get_hazard_events("Texas", AS_OF, 30)


def test_health_skips_snowflake_in_mock_mode() -> None:
    report = health_check()
    assert report == {"status": "ok", "use_mock_data": True, "snowflake": "skipped"}
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == report


def test_health_reports_unavailable_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_DATA", "false")
    for key in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD", "SNOWFLAKE_WAREHOUSE"):
        monkeypatch.setenv(key, "")
    report = health_check()
    assert report["status"] == "degraded"
    assert report["snowflake"] == "unavailable"
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["snowflake"] == "unavailable"
