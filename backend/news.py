"""News risk from BBC_NEWS, classified locally and cached without article text.

The live table is ``BBCGOOGLECNN_NEWS_LISTING.PUBLIC.BBC_NEWS``. Every column
is VARCHAR. ``PUBLICATION_DATE`` is a UTC timestamp string, sometimes wrapped
in quotes (``"2024-02-23T18:18:11.000Z"``). Place names are not columns: a row
matches when the city name appears in ``HEADLINE``. The scan drops rows
older than six months before that comparison. ``CONTENT`` is not searched.
The live table covers 2022 through 2024. An as-of date outside that range
skips the query.

Article bodies are licensed. They are read only long enough to classify an
uncached id, then dropped. SQLite stores the classification. Public results
contain the source id, headline, and date, plus the classification fields on
the risk response. They never contain ``CONTENT``.
"""

import json
import os
import re
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from snowflake_client import fetch_all, qualified_table, use_mock_data

REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_NEWS_PATH = REPO_ROOT / "data" / "mock_news.json"
DEFAULT_NEWS_TABLE = "BBCGOOGLECNN_NEWS_LISTING.PUBLIC.BBC_NEWS"
DEFAULT_LOOKBACK_DAYS = 7.0
NEWS_SCAN_MONTHS = 6
BBC_COVERAGE_START = datetime(2022, 1, 1, tzinfo=UTC)
BBC_COVERAGE_END = datetime(2025, 1, 1, tzinfo=UTC)
RECENCY_HALFLIFE_DAYS = 7.0
MAX_CLASSIFY_CHARS = 4000
_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS classifications (
    article_id TEXT PRIMARY KEY,
    relevant INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    severity INTEGER NOT NULL,
    affects_road_travel INTEGER NOT NULL
)
"""
EventType = Literal[
    "weather",
    "disaster",
    "accident",
    "strike",
    "protest",
    "road_closure",
    "infrastructure",
    "other",
]
_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


class NewsClassification(BaseModel):
    """Fixed label produced by the local model."""

    model_config = ConfigDict(extra="ignore")

    relevant: bool
    event_type: EventType
    severity: int
    affects_road_travel: bool

    @field_validator("severity")
    @classmethod
    def severity_band(cls, value: int) -> int:
        if value not in (0, 1, 2, 3):
            raise ValueError("severity must be an integer from 0 to 3")
        return value


def get_news_for_city(
    city: object,
    as_of_date: date | datetime,
    lookback_days: float,
) -> list[dict[str, object]]:
    """Return articles whose headline names the city inside the date window.

    Each item is ``id``, ``headline``, and ``date`` only.
    """
    as_of = _as_utc(as_of_date)
    window = _lookback(lookback_days)
    rows = _match_headlines([city], as_of, as_of - timedelta(days=window))
    name, _state = _search_terms(city)
    return [_public_article(row) for row in rows if _headline_mentions(str(row["headline"]), name)]


def news_risk_for_city(
    city: object,
    as_of_date: date | datetime,
    lookback_days: float | None = None,
) -> dict[str, object]:
    """Score road-affecting news and compare it with the previous window.

    An article contributes ``(severity / 3) * recency`` when its classification
    is relevant and ``affects_road_travel`` is true. ``severity`` is the model
    integer from 0 to 3. ``recency = 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)``
    with a 7-day half-life. The city score is the sum of those contributions,
    capped at 1. No contributing articles produces 0.

    Trend compares the count of those road-affecting articles with the count in
    the immediately previous window of the same length. ``rising`` means the
    current count is higher, ``falling`` means it is lower, and ``flat`` means
    the counts are equal.
    """
    window = DEFAULT_LOOKBACK_DAYS if lookback_days is None else _lookback(lookback_days)
    as_of = _as_utc(as_of_date)
    grouped = news_risks_for_cities([city], as_of, window)
    return grouped[_city_key(city)]


def news_risks_for_cities(
    cities: list[object],
    as_of_date: date | datetime,
    lookback_days: float | None = None,
) -> dict[str, dict[str, object]]:
    """Score every city from one headline query covering both trend windows."""
    if not cities:
        return {}
    window = DEFAULT_LOOKBACK_DAYS if lookback_days is None else _lookback(lookback_days)
    as_of = _as_utc(as_of_date)
    span_start = as_of - timedelta(days=2 * window)
    prepared = _classify_rows(_match_headlines(cities, as_of, span_start))
    current_start = as_of - timedelta(days=window)
    scores: dict[str, dict[str, object]] = {}
    for city in cities:
        name, _state = _search_terms(city)
        mine = [row for row in prepared if _headline_mentions(str(row["headline"]), name)]
        current = [row for row in mine if _in_window(row["published_at"], as_of, current_start)]
        prior = [row for row in mine if _in_window(row["published_at"], current_start, span_start)]
        scores[_city_key(city)] = _risk_from_windows(current, prior, as_of)
    return scores


def _risk_from_windows(
    current: list[dict[str, object]],
    prior: list[dict[str, object]],
    as_of: datetime,
) -> dict[str, object]:
    scored = [_with_contribution(row, as_of) for row in current if _counts_for_risk(row)]
    scored.sort(key=lambda row: float(row["contribution"]), reverse=True)
    total = sum(float(row["contribution"]) for row in scored)
    score = min(1.0, total)
    current_count = len(scored)
    prior_count = sum(1 for row in prior if _counts_for_risk(row))
    if current_count > prior_count:
        direction = "rising"
    elif current_count < prior_count:
        direction = "falling"
    else:
        direction = "flat"
    articles = [
        {
            "id": row["id"],
            "headline": row["headline"],
            "date": row["date"],
            "event_type": row["event_type"],
            "severity": row["severity"],
        }
        for row in scored
    ]
    return {
        "score": score,
        "factors": [
            {"name": "matched_articles", "value": len(current), "unit": "articles"},
            {"name": "road_affecting_articles", "value": current_count, "unit": "articles"},
            {"name": "prior_road_affecting_articles", "value": prior_count, "unit": "articles"},
            {"name": "news_risk", "value": score, "unit": "0-1"},
        ],
        "articles": articles,
        "trend": {
            "direction": direction,
            "current_road_events": current_count,
            "prior_road_events": prior_count,
        },
    }


def classify_article(article_id: str, headline: str, content: str) -> NewsClassification:
    """Classify one article, using the SQLite cache when this id was seen before."""
    cached = _cache_get(article_id)
    if cached is not None:
        return cached
    try:
        raw = _ollama_generate(_classification_prompt(headline, content))
        parsed = NewsClassification.model_validate(_parse_json_object(raw))
    except (ValueError, ValidationError, json.JSONDecodeError, httpx.HTTPError, KeyError):
        parsed = _irrelevant()
    _cache_put(article_id, parsed)
    return parsed


def ollama_request_body(prompt: str, model: str) -> dict[str, object]:
    """JSON-only generate request at temperature 0."""
    return {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }


def news_match_sql(table: str, city_count: int) -> str:
    """One headline query. The six-month cutoff is applied before the text match."""
    if city_count < 1:
        raise ValueError("city_count must be at least 1")
    clauses = " OR ".join(
        f"headline ILIKE %(city_{index})s ESCAPE '\\\\'" for index in range(city_count)
    )
    published = "TRY_TO_TIMESTAMP_TZ(TRIM(PUBLICATION_DATE, '\"'))"
    return f"""
        SELECT id, headline, published_at
        FROM (
            SELECT
                ID AS id,
                HEADLINE AS headline,
                CONVERT_TIMEZONE('UTC', {published}) AS published_at
            FROM {qualified_table(table)}
            WHERE {published} <= %(as_of)s
              AND {published} > DATEADD(month, %(scan_months)s, %(as_of)s)
        ) AS articles
        WHERE published_at IS NOT NULL
          AND published_at <= %(as_of)s
          AND published_at > %(window_start)s
          AND ({clauses})
    """


def like_contains(term: str) -> str:
    """Bind pattern that matches a term anywhere, with ``%`` and ``_`` escaped."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _classify_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if use_mock_data():
        for row in rows:
            row["classification"] = _mock_classification(row)
        return rows
    missing = [str(row["id"]) for row in rows if _cache_get(str(row["id"])) is None]
    bodies = _fetch_bodies(missing) if missing else {}
    for row in rows:
        article_id = str(row["id"])
        cached = _cache_get(article_id)
        if cached is None:
            cached = classify_article(article_id, str(row["headline"]), bodies.get(article_id, ""))
        row["classification"] = cached
    return rows


def _match_headlines(
    cities: list[object],
    as_of: datetime,
    window_start: datetime,
) -> list[dict[str, object]]:
    """Articles in the window whose headline names one of the cities."""
    names = []
    for city in cities:
        name, _state = _search_terms(city)
        if name.casefold() not in {item.casefold() for item in names}:
            names.append(name)
    if not names:
        return []
    if use_mock_data():
        return [
            row
            for row in _load_mock_rows()
            if _in_window(row["published_at"], as_of, window_start)
            and any(_headline_mentions(str(row["headline"]), name) for name in names)
        ]
    if not _within_bbc_coverage(as_of):
        return []
    params: dict[str, object] = {
        "as_of": as_of.replace(tzinfo=None),
        "window_start": window_start.replace(tzinfo=None),
        "scan_months": -NEWS_SCAN_MONTHS,
    }
    for index, name in enumerate(names):
        params[f"city_{index}"] = like_contains(name)
    table = os.environ.get("SNOWFLAKE_NEWS_TABLE", "").strip() or DEFAULT_NEWS_TABLE
    queried = fetch_all(news_match_sql(table, len(names)), params)
    rows: list[dict[str, object]] = []
    for row in queried:
        published = _parse_time(row.get("published_at"))
        if published is None or not row.get("id"):
            continue
        rows.append(
            {
                "id": str(row["id"]),
                "headline": str(row.get("headline") or ""),
                "published_at": published,
            }
        )
    return rows


def _within_bbc_coverage(as_of: datetime) -> bool:
    """True when the as-of instant falls in the BBC table's 2022–2024 coverage."""
    moment = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    return BBC_COVERAGE_START <= moment < BBC_COVERAGE_END


def _headline_mentions(headline: str, city_name: str) -> bool:
    return city_name.casefold() in headline.casefold()


def _city_key(city: object) -> str:
    if isinstance(city, dict) and city.get("id"):
        return str(city["id"])
    if getattr(city, "id", None):
        return str(city.id)
    name, _state = _search_terms(city)
    return name.casefold()


def _fetch_bodies(article_ids: list[str]) -> dict[str, str]:
    """Load licensed text for uncached ids. Callers must not keep the strings."""
    table = os.environ.get("SNOWFLAKE_NEWS_TABLE", "").strip() or DEFAULT_NEWS_TABLE
    found: dict[str, str] = {}
    for start in range(0, len(article_ids), 50):
        chunk = article_ids[start : start + 50]
        params = {f"id_{index}": article_id for index, article_id in enumerate(chunk)}
        placeholders = ", ".join(f"%(id_{index})s" for index in range(len(chunk)))
        sql = f"""
            SELECT ID AS id, CONTENT AS content
            FROM {qualified_table(table)}
            WHERE ID IN ({placeholders})
        """
        for row in fetch_all(sql, params):
            if row.get("id") is not None:
                found[str(row["id"])] = str(row.get("content") or "")
    return found


def _mock_classification(row: dict[str, object]) -> NewsClassification:
    cached = _cache_get(str(row["id"]))
    if cached is not None:
        return cached
    try:
        parsed = NewsClassification.model_validate(row.get("classification") or {})
    except ValidationError:
        parsed = _irrelevant()
    _cache_put(str(row["id"]), parsed)
    return parsed


def _counts_for_risk(row: dict[str, object]) -> bool:
    label = row["classification"]
    return isinstance(label, NewsClassification) and label.relevant and label.affects_road_travel


def _with_contribution(row: dict[str, object], as_of: datetime) -> dict[str, object]:
    label = row["classification"]
    assert isinstance(label, NewsClassification)
    published = row["published_at"]
    assert isinstance(published, datetime)
    age_days = max(0.0, (as_of - published).total_seconds() / 86400)
    recency = 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)
    public = _public_article(row)
    public["event_type"] = label.event_type
    public["severity"] = label.severity
    public["contribution"] = (label.severity / 3) * recency
    return public


def _public_article(row: dict[str, object]) -> dict[str, object]:
    published = row["published_at"]
    assert isinstance(published, datetime)
    return {
        "id": row["id"],
        "headline": row["headline"],
        "date": published.astimezone(UTC).isoformat(),
    }


def _in_window(published: object, as_of: datetime, window_start: datetime) -> bool:
    return isinstance(published, datetime) and window_start < published <= as_of


def _search_terms(city: object) -> tuple[str, str | None]:
    if isinstance(city, str):
        name, state = city, ""
    elif isinstance(city, dict):
        name, state = str(city.get("name") or ""), str(city.get("state") or "")
    else:
        name = str(getattr(city, "name", "") or "")
        state = str(getattr(city, "state", "") or "")
    city_name = " ".join(name.split())
    state_name = _state_name(state)
    if len(city_name) < 3:
        raise ValueError("city name must be at least 3 characters")
    if state_name is not None and len(state_name) < 3:
        state_name = None
    return city_name, state_name


def _state_name(state: str) -> str | None:
    text = " ".join(state.split())
    if not text:
        return None
    if len(text) == 2:
        return _STATE_NAMES.get(text.upper())
    return text


def _load_mock_rows() -> list[dict[str, object]]:
    payload = json.loads(MOCK_NEWS_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for item in payload:
        published = _parse_time(item.get("publication_date"))
        if published is None or not item.get("id"):
            continue
        rows.append(
            {
                "id": str(item["id"]),
                "headline": str(item.get("headline") or ""),
                "published_at": published,
                "content": str(item.get("content") or ""),
                "classification": item.get("classification"),
            }
        )
    return rows


def _classification_prompt(headline: str, content: str) -> str:
    excerpt = content[:MAX_CLASSIFY_CHARS]
    return (
        "Classify this news article for truck-route risk. "
        "Reply with one JSON object and no other text. "
        'Schema: {"relevant": bool, "event_type": '
        '"weather|disaster|accident|strike|protest|road_closure|infrastructure|other", '
        '"severity": 0|1|2|3, "affects_road_travel": bool}. '
        "relevant is true only for a real-world disruption. "
        "severity 0 is none and 3 is severe. "
        "affects_road_travel is true only when roads, transit, or freight movement are disrupted.\n"
        f"Headline: {headline}\n"
        f"Article text: {excerpt}"
    )


def _ollama_generate(prompt: str) -> str:
    if os.environ.get("EXPLAIN_PROVIDER", "ollama").strip().lower() == "cloud":
        return _cloud_generate(prompt)
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    response = httpx.post(
        f"{base}/api/generate",
        json=ollama_request_body(prompt, model),
        timeout=httpx.Timeout(120.0, connect=3.0),
    )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("response")
    if not isinstance(text, str):
        raise ValueError("Ollama returned no text")
    return text


def _cloud_generate(prompt: str) -> str:
    """OpenAI-compatible chat call used when explanations run on the cloud model."""
    base = os.environ.get("CLOUD_MODEL_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("CLOUD_MODEL_BASE_URL is not set")
    model = os.environ.get("CLOUD_MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
    key = os.environ.get("CLOUD_MODEL_API_KEY", "").strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    response = httpx.post(
        url,
        headers=headers,
        json={
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=httpx.Timeout(120.0, connect=3.0),
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    if not isinstance(text, str):
        raise ValueError("cloud model returned no text")
    return text


def _parse_json_object(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("classification must be a JSON object")
    return value


def _irrelevant() -> NewsClassification:
    return NewsClassification(
        relevant=False,
        event_type="other",
        severity=0,
        affects_road_travel=False,
    )


def _cache_path() -> Path:
    override = os.environ.get("NEWS_CACHE_PATH", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / "data" / "news_classification_cache.sqlite"


def _cache_get(article_id: str) -> NewsClassification | None:
    with _cache_connection() as conn:
        found = conn.execute(
            """
            SELECT relevant, event_type, severity, affects_road_travel
            FROM classifications
            WHERE article_id = ?
            """,
            (article_id,),
        ).fetchone()
    if found is None:
        return None
    return NewsClassification(
        relevant=bool(found[0]),
        event_type=found[1],
        severity=found[2],
        affects_road_travel=bool(found[3]),
    )


def _cache_put(article_id: str, label: NewsClassification) -> None:
    with _cache_connection() as conn:
        conn.execute(
            """
            INSERT INTO classifications (
                article_id, relevant, event_type, severity, affects_road_travel
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO NOTHING
            """,
            (
                article_id,
                int(label.relevant),
                label.event_type,
                label.severity,
                int(label.affects_road_travel),
            ),
        )
        conn.commit()


def _cache_connection() -> sqlite3.Connection:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_CACHE_DDL)
    return conn


def _as_utc(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=UTC)
    raise TypeError("as_of_date must be a date or datetime")


def _lookback(days: float) -> float:
    if days < 0:
        raise ValueError("lookback_days must be non-negative")
    return float(days)


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    text = str(value).strip().strip('"')
    if not text or text.lower() == "null":
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
