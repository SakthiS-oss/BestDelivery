"""HTTP contract for plan, cities, city risk, and health."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import RequestTimeoutMiddleware, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def force_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_DATA", "true")


def test_health_reports_mock_mode_on_both_paths() -> None:
    for path in ("/health", "/api/health"):
        body = client.get(path).json()
        assert body["status"] == "ok"
        assert body["use_mock_data"] is True
        assert body["snowflake"] == "skipped"
        assert body["ollama"] == "skipped"


def test_cities_lists_dallas() -> None:
    response = client.get("/cities")
    assert response.status_code == 200
    labels = {row["label"] for row in response.json()}
    assert "Dallas, TX" in labels
    assert "Atlanta, GA" in labels


def test_unknown_city_is_a_clear_400() -> None:
    response = client.post(
        "/plan",
        json={"start": "Atlantis", "end": "Atlanta, GA", "deadline": 72, "as_of_date": "2026-06-15"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "unknown city: Atlantis"


def test_unknown_city_risk_is_a_clear_400() -> None:
    response = client.get("/city/Atlantis/risk", params={"as_of_date": "2026-06-15"})
    assert response.status_code == 400
    assert response.json()["detail"] == "unknown city: Atlantis"


def test_plan_ranks_dallas_to_atlanta() -> None:
    response = client.post(
        "/plan",
        json={"start": "Dallas, TX", "end": "Atlanta, GA", "deadline": 72, "as_of_date": "2026-06-15"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["warnings"] == []
    assert body["deadline_hours"] == 72
    assert body["routes"]
    assert body["routes"][0]["id"] == "route-1"
    assert body["baseline"]["id"] == "baseline"
    assert [city["name"] for city in body["baseline"]["cities"]][0] == "Dallas"


def test_city_risk_returns_hazard_and_news() -> None:
    response = client.get("/city/Houston/risk", params={"as_of_date": "2026-06-15"})
    assert response.status_code == 200
    body = response.json()
    assert body["city"]["label"] == "Houston, TX"
    assert body["warnings"] == []
    assert "score" in body["hazard"]
    assert "events" in body["hazard"]
    assert "articles" in body["news"]


def test_snowflake_outage_returns_partial_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("missing Snowflake settings: account")

    monkeypatch.setattr("hazards.hazard_risk_for_city", down)
    monkeypatch.setattr("hazards.hazard_risk_for_edge", down)
    response = client.post(
        "/plan",
        json={"start": "Dallas", "end": "Houston", "deadline": 48, "as_of_date": "2026-06-15"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["routes"]
    assert body["routes"][0]["hazard_risk_max"] == 0
    assert "Snowflake is unavailable; hazard scores were omitted." in body["warnings"]


def test_openapi_includes_plan_example() -> None:
    schema = client.get("/openapi.json").json()
    example = schema["components"]["schemas"]["PlanRequest"]["example"]
    assert example["start"] == "Dallas, TX"
    assert example["deadline"] == 72
    post = schema["paths"]["/plan"]["post"]
    assert post["requestBody"]["content"]["application/json"]["examples"]["dallas_to_atlanta"]["value"] == example


def test_localhost_frontend_is_allowed() -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    blocked = client.get("/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in blocked.headers


def test_request_timeout_returns_504() -> None:
    app_with_timeout = FastAPI()

    @app_with_timeout.get("/slow")
    async def slow() -> dict[str, bool]:
        await asyncio.sleep(0.3)
        return {"ok": True}

    app_with_timeout.add_middleware(RequestTimeoutMiddleware, timeout_seconds=0.05)
    response = TestClient(app_with_timeout).get("/slow")
    assert response.status_code == 504
    assert response.json()["detail"] == "request timed out"
