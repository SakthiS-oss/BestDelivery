"""News matching, mocked classification, and risk scores. No live model calls."""

import json
from datetime import UTC, datetime

import pytest

from news import (
    RECENCY_HALFLIFE_DAYS,
    classify_article,
    get_news_for_city,
    like_contains,
    news_match_sql,
    news_risk_for_city,
    ollama_request_body,
)
from snowflake_client import assert_select_only

AS_OF = datetime(2026, 6, 15, tzinfo=UTC)
CHICAGO = {"name": "Chicago", "lat": 41.8781, "lon": -87.6298, "state": "IL"}
ROAD_LABEL = {
    "relevant": True,
    "event_type": "road_closure",
    "severity": 3,
    "affects_road_travel": True,
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("USE_MOCK_DATA", "true")
    monkeypatch.setenv("NEWS_CACHE_PATH", str(tmp_path / "news.sqlite"))


def test_headline_match_inside_the_window() -> None:
    articles = get_news_for_city(CHICAGO, AS_OF, 7)
    assert {article["id"] for article in articles} == {
        "chi-road",
        "chi-bridge",
        "chi-sports",
    }
    for article in articles:
        assert set(article) == {"id", "headline", "date"}
        assert "content" not in article


def test_news_sql_filters_in_sql_and_does_not_return_text() -> None:
    sql = news_match_sql("BBCGOOGLECNN_NEWS_LISTING.PUBLIC.BBC_NEWS", 2)
    assert_select_only(sql)
    assert sql.strip().startswith("SELECT id, headline, published_at")
    assert "DATEADD(month, %(scan_months)s, %(as_of)s)" in sql
    assert "headline ILIKE %(city_0)s" in sql
    assert "headline ILIKE %(city_1)s" in sql
    assert "ESCAPE '\\\\'" in sql
    assert "CONTENT" not in sql
    assert "Chicago" not in sql
    assert like_contains("100%_Chicago") == "%100\\%\\_Chicago%"


def test_mock_risk_score_trend_and_no_article_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("mock mode must not call Ollama")

    monkeypatch.setattr("news._ollama_generate", boom)
    result = news_risk_for_city(CHICAGO, AS_OF, lookback_days=7)
    ids = [article["id"] for article in result["articles"]]
    assert ids == ["chi-road", "chi-bridge"]
    assert "chi-sports" not in ids
    assert "state-storm" not in ids
    assert "chi-old" not in ids
    assert "dal-crash" not in ids
    total = sum(_expected_contribution(article) for article in result["articles"])
    assert result["score"] == pytest.approx(min(1.0, total))
    assert 0 < float(result["score"]) <= 1
    assert result["trend"] == {
        "direction": "flat",
        "current_road_events": 2,
        "prior_road_events": 2,
    }
    encoded = json.dumps(result)
    assert "Standing water shut lanes" not in encoded
    assert "content" not in encoded


def test_live_path_classifies_once_and_drops_the_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("USE_MOCK_DATA", "false")
    calls = {"model": 0, "bodies": 0}
    licensed = "Unique licensed sentence that must stay off disk."

    def fake_match(
        cities: list[object],
        as_of: datetime,
        window_start: datetime,
    ) -> list[dict[str, object]]:
        published = datetime(2026, 6, 14, tzinfo=UTC)
        if window_start < published <= as_of:
            return [
                {
                    "id": "live-1",
                    "headline": "Chicago highway closed",
                    "published_at": published,
                }
            ]
        return []

    def fake_bodies(article_ids: list[str]) -> dict[str, str]:
        calls["bodies"] += 1
        assert article_ids == ["live-1"]
        return {"live-1": licensed}

    def fake_model(prompt: str) -> str:
        calls["model"] += 1
        assert licensed in prompt
        return json.dumps(ROAD_LABEL)

    monkeypatch.setattr("news._match_headlines", fake_match)
    monkeypatch.setattr("news._fetch_bodies", fake_bodies)
    monkeypatch.setattr("news._ollama_generate", fake_model)

    first = news_risk_for_city(CHICAGO, AS_OF, lookback_days=7)
    second = news_risk_for_city(CHICAGO, AS_OF, lookback_days=7)
    assert calls == {"model": 1, "bodies": 1}
    assert first["articles"] == second["articles"]
    assert first["articles"][0]["event_type"] == "road_closure"
    assert set(first["articles"][0]) == {"id", "headline", "date", "event_type", "severity"}
    stored = (tmp_path / "news.sqlite").read_bytes()
    assert licensed.encode() not in stored
    assert b"Chicago highway closed" not in stored


def test_bad_model_output_falls_back_and_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_model(_prompt: str) -> str:
        calls["n"] += 1
        return "not json"

    monkeypatch.setattr("news._ollama_generate", fake_model)
    first = classify_article("bad-1", "Headline", "Body text")
    second = classify_article("bad-1", "Headline", "Body text")
    assert calls["n"] == 1
    assert first.relevant is False
    assert second == first

    def out_of_range(_prompt: str) -> str:
        calls["n"] += 1
        return json.dumps({**ROAD_LABEL, "severity": 9})

    monkeypatch.setattr("news._ollama_generate", out_of_range)
    rejected = classify_article("bad-2", "Headline", "Body text")
    assert rejected.relevant is False
    assert calls["n"] == 2


def test_live_news_skips_dates_outside_2022_through_2024(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_DATA", "false")

    def boom(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("news query should not run")

    monkeypatch.setattr("news.fetch_all", boom)
    outside = news_risk_for_city(CHICAGO, AS_OF, lookback_days=7)
    assert outside["score"] == 0
    assert outside["articles"] == []
    assert outside["trend"]["direction"] == "flat"
    assert get_news_for_city(CHICAGO, datetime(2021, 12, 31, tzinfo=UTC), 7) == []

    calls = {"n": 0}

    def fake_fetch(_sql: str, _params: object = None) -> list[dict[str, object]]:
        calls["n"] += 1
        return []

    monkeypatch.setattr("news.fetch_all", fake_fetch)
    news_risk_for_city(CHICAGO, datetime(2024, 6, 15, tzinfo=UTC), lookback_days=7)
    news_risk_for_city(CHICAGO, datetime(2022, 1, 1, tzinfo=UTC), lookback_days=7)
    news_risk_for_city(CHICAGO, datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC), lookback_days=7)
    assert calls["n"] == 3
    news_risk_for_city(CHICAGO, datetime(2025, 1, 1, tzinfo=UTC), lookback_days=7)
    assert calls["n"] == 3


def test_ollama_request_is_json_at_temperature_zero() -> None:
    body = ollama_request_body("classify", "llama3.2")
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0}


def _expected_contribution(article: dict[str, object]) -> float:
    published = datetime.fromisoformat(str(article["date"]))
    age_days = max(0.0, (AS_OF - published).total_seconds() / 86400)
    recency = 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)
    return (int(article["severity"]) / 3) * recency
