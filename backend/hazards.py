"""Hazard events from Snowflake or data/mock_hazards.json, and their risk scores.

Schema notes for ND_ACTUALS, taken from the live table and the sample rows:

- Longitude is ``lng``. ``lon`` is empty in the sample, so it is only a fallback.
- ``date`` is a VARIANT string. In the sample it reconciles with ``local_time``
  through ``utc_offset``, so it is treated as UTC. ``end_date`` and
  ``estimated_end_date`` use the same format.
- There is no severity column. Severity is derived from ``alert_level`` and the
  ``death`` / ``injured`` counts inside ``details``.
- A region string is matched to ``state`` as stored (full name, any case).
"""

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.routing.distance import haversine_miles
from snowflake_client import fetch_all, qualified_table, use_mock_data

REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_HAZARDS_PATH = REPO_ROOT / "data" / "mock_hazards.json"

# Tunable score weights. See hazard_risk_for_city.
ALERT_SEVERITY = {
    "green": 0.25,
    "yellow": 0.45,
    "orange": 0.70,
    "red": 1.00,
}
UNKNOWN_ALERT_SEVERITY = 0.40
DEATH_WEIGHT = 0.15
INJURY_WEIGHT = 0.02
CITY_RADIUS_MILES = 100.0
RECENCY_HALFLIFE_DAYS = 14.0
DEFAULT_LOOKBACK_DAYS = 30.0
EDGE_SAMPLE_COUNT = 5
MILES_PER_LAT_DEGREE = 69.0


def get_hazard_events(
    region_or_bbox: str | dict[str, float] | tuple[float, float, float, float] | list[float],
    as_of_date: date | datetime,
    lookback_days: float,
) -> list[dict[str, object]]:
    """Return hazards active in the lookback window and inside the region.

    ``region_or_bbox`` is either a state name (``"Illinois"``) or a box
    ``(min_lat, min_lon, max_lat, max_lon)``. A date-only ``as_of_date`` means
    the end of that UTC day.

    An event is inside the window when its start is at or before ``as_of`` and
    its end is at or after the start of the window. ``end_date`` wins, then
    ``estimated_end_date``. If both are missing, the event is instantaneous at
    ``date`` and counts only when that instant is inside the window.
    """
    as_of = _as_utc(as_of_date)
    window_start = as_of - timedelta(days=_lookback(lookback_days))
    region = _parse_region(region_or_bbox)
    if use_mock_data():
        rows = _load_mock_rows()
    else:
        rows = _fetch_snowflake(region, as_of, window_start)
    return [
        _public_event(row)
        for row in rows
        if _in_region(row, region) and _in_window(row, as_of, window_start)
    ]


def hazard_risk_for_city(
    city: object,
    as_of_date: date | datetime,
    lookback_days: float = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, object]:
    """Score hazards within ``CITY_RADIUS_MILES`` of a city.

    Each event contributes ``severity * recency * proximity``, and the city
    score is the sum of those contributions capped at 1.

    ``severity = min(1, max(alert_weight, deaths * DEATH_WEIGHT + injured * INJURY_WEIGHT))``
    Alert weights live in ``ALERT_SEVERITY``. Unknown levels use
    ``UNKNOWN_ALERT_SEVERITY``. Casualty counts can raise a low alert; they
    cannot lower a high one.

    ``recency = 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)`` from the event start.
    ``proximity = max(0, 1 - distance_miles / CITY_RADIUS_MILES)``.
    """
    name, lat, lon = _place(city)
    events = _events_near(lat, lon, CITY_RADIUS_MILES, as_of_date, lookback_days)
    return _aggregate(name, events)


def hazard_risk_for_edge(
    origin: object,
    destination: object,
    as_of_date: date | datetime,
    lookback_days: float = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, object]:
    """Score a road segment as the maximum risk among sampled points.

    ``EDGE_SAMPLE_COUNT`` points (default 5, including both endpoints) are
    spaced by linear interpolation in latitude and longitude. Each point uses
    the city formula. The edge score is the max of those point scores, so one
    severe hazard along the segment is not averaged away.
    """
    if EDGE_SAMPLE_COUNT < 2:
        raise ValueError("EDGE_SAMPLE_COUNT must be at least 2")
    _, lat1, lon1 = _place(origin)
    _, lat2, lon2 = _place(destination)
    samples: list[dict[str, object]] = []
    best_events: list[dict[str, object]] = []
    best_score = 0.0
    for index in range(EDGE_SAMPLE_COUNT):
        fraction = index / (EDGE_SAMPLE_COUNT - 1)
        lat = lat1 + fraction * (lat2 - lat1)
        lon = lon1 + fraction * (lon2 - lon1)
        events = _events_near(lat, lon, CITY_RADIUS_MILES, as_of_date, lookback_days)
        point = _aggregate(f"sample-{index}", events)
        score = float(point["score"])
        samples.append({"lat": lat, "lon": lon, "score": score})
        if score >= best_score:
            best_score = score
            best_events = [dict(event) for event in events]
    return {
        "score": best_score,
        "aggregation": "max",
        "factors": [
            {
                "name": "sample_hazard_risk",
                "value": sample["score"],
                "unit": "0-1",
                "lat": sample["lat"],
                "lon": sample["lon"],
            }
            for sample in samples
        ]
        + [{"name": "hazard_risk", "value": best_score, "unit": "0-1"}],
        "events": best_events,
        "samples": samples,
    }


def load_mock_hazards() -> list[dict[str, object]]:
    """Read every mock hazard, including rows outside a caller's time window."""
    return [_public_event(row) for row in _load_mock_rows()]


def _events_near(
    lat: float,
    lon: float,
    radius_miles: float,
    as_of_date: date | datetime,
    lookback_days: float,
) -> list[dict[str, object]]:
    lat_pad = radius_miles / MILES_PER_LAT_DEGREE
    lon_scale = max(0.2, abs(math.cos(math.radians(lat))))
    lon_pad = radius_miles / (MILES_PER_LAT_DEGREE * lon_scale)
    rows = get_hazard_events(
        (lat - lat_pad, lon - lon_pad, lat + lat_pad, lon + lon_pad),
        as_of_date,
        lookback_days,
    )
    as_of = _as_utc(as_of_date)
    scored: list[dict[str, object]] = []
    for row in rows:
        distance = haversine_miles(lat, lon, float(row["lat"]), float(row["lon"]))
        proximity = max(0.0, 1.0 - distance / radius_miles)
        if proximity <= 0:
            continue
        start = _parse_time(row["start_time"])
        assert start is not None
        age_days = max(0.0, (as_of - start).total_seconds() / 86400)
        severity = _severity(str(row["alert_level"]), row["details"])
        recency = 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)
        contribution = severity * recency * proximity
        scored.append(
            {
                **row,
                "distance_miles": distance,
                "severity": severity,
                "recency": recency,
                "proximity": proximity,
                "contribution": contribution,
            }
        )
    scored.sort(key=lambda item: float(item["contribution"]), reverse=True)
    return scored


def _aggregate(label: str, events: list[dict[str, object]]) -> dict[str, object]:
    total = sum(float(event["contribution"]) for event in events)
    score = min(1.0, total)
    factors: list[dict[str, object]] = []
    for event in events:
        for name in ("severity", "recency", "proximity", "contribution"):
            factors.append(
                {
                    "name": name,
                    "event_id": event["event_id"],
                    "value": event[name],
                    "unit": "0-1",
                }
            )
    factors.append({"name": "hazard_risk", "place": label, "value": score, "unit": "0-1"})
    return {"score": score, "factors": factors, "events": events}


def _severity(alert_level: str, details: object) -> float:
    alert = ALERT_SEVERITY.get(alert_level.strip().lower(), UNKNOWN_ALERT_SEVERITY)
    payload = details if isinstance(details, dict) else {}
    deaths = _count(payload, "death", "deaths")
    injured = _count(payload, "injured", "injuries")
    casualty = min(1.0, deaths * DEATH_WEIGHT + injured * INJURY_WEIGHT)
    return min(1.0, max(alert, casualty))


def _count(details: dict[str, object], *keys: str) -> float:
    for key in keys:
        value = details.get(key)
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
    return 0.0


def _fetch_snowflake(
    region: dict[str, object],
    as_of: datetime,
    window_start: datetime,
) -> list[dict[str, object]]:
    table = qualified_table()
    by_state = region["kind"] == "state"
    params: dict[str, object] = {
        "as_of": as_of.replace(tzinfo=None),
        "window_start": window_start.replace(tzinfo=None),
    }
    if by_state:
        params["state"] = region["state"]
    else:
        params["min_lat"] = region["min_lat"]
        params["max_lat"] = region["max_lat"]
        params["min_lon"] = region["min_lon"]
        params["max_lon"] = region["max_lon"]
    queried = fetch_all(_events_sql(table, by_state=by_state), params)
    rows: list[dict[str, object]] = []
    for row in queried:
        start = _parse_time(row.get("start_time"))
        if start is None or row.get("lat") is None or row.get("lon") is None:
            continue
        rows.append(
            {
                "event_id": str(row.get("event_id") or ""),
                "event_type": str(row.get("event_type") or ""),
                "event_name": str(row.get("event_name") or ""),
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "start_time": start,
                "end_time": _parse_time(row.get("end_time")) or _parse_time(row.get("estimated_end_time")),
                "city": str(row.get("city") or ""),
                "state": str(row.get("state") or ""),
                "country_code": str(row.get("country_code") or ""),
                "alert_level": str(row.get("alert_level") or ""),
                "details": _details(row.get("details")),
            }
        )
    return rows


def _events_sql(table: str, *, by_state: bool) -> str:
    location = (
        "UPPER(state) = UPPER(%(state)s)"
        if by_state
        else "lat BETWEEN %(min_lat)s AND %(max_lat)s AND longitude BETWEEN %(min_lon)s AND %(max_lon)s"
    )
    return f"""
        SELECT
            event_id,
            event_type,
            event_name,
            lat,
            longitude AS lon,
            start_ts AS start_time,
            end_ts AS end_time,
            est_end_ts AS estimated_end_time,
            city,
            state,
            country_code,
            alert_level,
            details
        FROM (
            SELECT
                event_id,
                event_type,
                event_name,
                lat,
                COALESCE(lng, lon) AS longitude,
                TRY_TO_TIMESTAMP_NTZ(TO_VARCHAR(date)) AS start_ts,
                TRY_TO_TIMESTAMP_NTZ(TO_VARCHAR(end_date)) AS end_ts,
                TRY_TO_TIMESTAMP_NTZ(TO_VARCHAR(estimated_end_date)) AS est_end_ts,
                city,
                state,
                country_code,
                alert_level,
                details
            FROM {table}
        ) AS hazards
        WHERE lat IS NOT NULL
          AND longitude IS NOT NULL
          AND start_ts IS NOT NULL
          AND start_ts <= %(as_of)s
          AND COALESCE(end_ts, est_end_ts, start_ts) >= %(window_start)s
          AND {location}
    """


def _load_mock_rows() -> list[dict[str, object]]:
    payload = json.loads(MOCK_HAZARDS_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for item in payload:
        start = _parse_time(item.get("date"))
        if start is None:
            continue
        rows.append(
            {
                "event_id": str(item["event_id"]),
                "event_type": str(item.get("event_type") or ""),
                "event_name": str(item.get("event_name") or ""),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "start_time": start,
                "end_time": _parse_time(item.get("end_date")) or _parse_time(item.get("estimated_end_date")),
                "city": str(item.get("city") or ""),
                "state": str(item.get("state") or ""),
                "country_code": str(item.get("country_code") or ""),
                "alert_level": str(item.get("alert_level") or ""),
                "details": _details(item.get("details")),
            }
        )
    return rows


def _public_event(row: dict[str, object]) -> dict[str, object]:
    end = row["end_time"]
    return {
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "event_name": row["event_name"],
        "lat": row["lat"],
        "lon": row["lon"],
        "start_time": row["start_time"],
        "end_time": end,
        "city": row["city"],
        "state": row["state"],
        "country_code": row["country_code"],
        "alert_level": row["alert_level"],
        "details": row["details"],
    }


def _in_window(row: dict[str, object], as_of: datetime, window_start: datetime) -> bool:
    start = row["start_time"]
    assert isinstance(start, datetime)
    if start > as_of:
        return False
    end = row["end_time"] if isinstance(row["end_time"], datetime) else start
    return end >= window_start


def _in_region(row: dict[str, object], region: dict[str, object]) -> bool:
    if region["kind"] == "state":
        return str(row["state"]).lower() == str(region["state"]).lower()
    lat = float(row["lat"])
    lon = float(row["lon"])
    return (
        float(region["min_lat"]) <= lat <= float(region["max_lat"])
        and float(region["min_lon"]) <= lon <= float(region["max_lon"])
    )


def _parse_region(
    region_or_bbox: str | dict[str, float] | tuple[float, float, float, float] | list[float],
) -> dict[str, object]:
    if isinstance(region_or_bbox, str):
        state = " ".join(region_or_bbox.split())
        if not state:
            raise ValueError("region is empty")
        return {"kind": "state", "state": state}
    if isinstance(region_or_bbox, dict):
        box = (
            region_or_bbox["min_lat"],
            region_or_bbox["min_lon"],
            region_or_bbox["max_lat"],
            region_or_bbox["max_lon"],
        )
    elif isinstance(region_or_bbox, (tuple, list)) and len(region_or_bbox) == 4:
        box = (
            float(region_or_bbox[0]),
            float(region_or_bbox[1]),
            float(region_or_bbox[2]),
            float(region_or_bbox[3]),
        )
    else:
        raise TypeError("region_or_bbox must be a state name or (min_lat, min_lon, max_lat, max_lon)")
    min_lat, min_lon, max_lat, max_lon = box
    if not -90 <= min_lat <= max_lat <= 90 or not -180 <= min_lon <= max_lon <= 180:
        raise ValueError("bounding box is out of range or reversed")
    return {
        "kind": "bbox",
        "min_lat": min_lat,
        "min_lon": min_lon,
        "max_lat": max_lat,
        "max_lon": max_lon,
    }


def _place(city: object) -> tuple[str, float, float]:
    if isinstance(city, dict):
        return str(city.get("name", "city")), float(city["lat"]), float(city["lon"])
    return str(getattr(city, "name", "city")), float(city.lat), float(city.lon)  # type: ignore[attr-defined]


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


def _details(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "null":
            return {}
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    return {}
