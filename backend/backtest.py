"""Historical replay of the planner against past disasters.

Plans are scored only with records dated on or before as_of. The disaster
being reviewed is not an input when as_of is three days before it starts.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import networkx as nx

from app.domain.models import City, Hop
from app.routing.cities import load_cities
from app.routing.distance import haversine_miles
from app.routing.edges import load_edges
from hazards import CITY_RADIUS_MILES, get_hazard_events, load_mock_hazards
from scoring import RankedRoutes, plan_routes

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "data" / "backtest_report.json"
OFFSET_DAYS = 3
DEADLINE_HOURS = 120.0
ALERT_RANK = {"red": 0, "orange": 1, "yellow": 2, "green": 3}

DISCLAIMER = (
    "These figures describe a historical replay. "
    "Each plan used only hazards and news dated on or before three days before the event. "
    "The event itself was not an input. "
    "The counts are evidence about those past cases, not a guarantee that a later disruption would be avoided."
)


def route_avoided(baseline_ids: list[str], proposed_ids: list[str], affected_ids: set[str]) -> bool:
    """True when every affected stop on the baseline interior is absent from the proposal."""
    danger = affected_ids.intersection(baseline_ids[1:-1])
    if not danger:
        return False
    return danger.isdisjoint(proposed_ids)


def affected_cities(event: dict[str, object], cities: list[City]) -> list[City]:
    """Catalog cities within the hazard radius of an event, nearest first."""
    lat = float(event["lat"])
    lon = float(event["lon"])
    named = str(event.get("city") or "").casefold()
    nearby: list[tuple[float, City]] = []
    for city in cities:
        miles = haversine_miles(lat, lon, city.lat, city.lon)
        same_name = bool(named) and city.name.casefold() == named
        if miles <= CITY_RADIUS_MILES or same_name:
            nearby.append((miles, city))
    nearby.sort(key=lambda item: (item[0], item[1].name))
    return [city for _miles, city in nearby]


def through_pairs(
    graph: nx.Graph,
    cities_by_id: dict[str, City],
    affected_ids: set[str],
    limit: int,
) -> list[tuple[City, City, list[str]]]:
    """Origin and destination pairs whose shortest path enters the affected set."""
    if limit < 1:
        return []
    candidates: list[tuple[int, str, str, list[str]]] = []
    for origin in graph.nodes:
        _lengths, paths = nx.single_source_dijkstra(graph, origin, weight="weight")
        for dest, path in paths.items():
            if str(origin) >= str(dest) or len(path) < 3:
                continue
            if not affected_ids.intersection(path[1:-1]):
                continue
            candidates.append((len(path), str(origin), str(dest), list(path)))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    chosen: list[tuple[City, City, list[str]]] = []
    used_origins: set[str] = set()
    unused: list[tuple[City, City, list[str]]] = []
    for _length, origin_id, dest_id, path in candidates:
        pair = (cities_by_id[origin_id], cities_by_id[dest_id], path)
        if origin_id in used_origins:
            unused.append(pair)
            continue
        used_origins.add(origin_id)
        chosen.append(pair)
        if len(chosen) == limit:
            return chosen
    for pair in unused:
        chosen.append(pair)
        if len(chosen) == limit:
            break
    return chosen


def run_backtest(
    *,
    events: int = 5,
    routes_per_event: int = 5,
    cities: list[City] | None = None,
    edges: list[Hop] | None = None,
    hazard_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Score sample corridors three days before each selected disaster."""
    if events < 1 or routes_per_event < 1:
        raise ValueError("events and routes_per_event must be at least 1")
    catalog = cities if cities is not None else load_cities(REPO_ROOT / "data" / "cities.csv")
    road_edges = edges if edges is not None else load_edges(REPO_ROOT / "data" / "edges.csv", catalog)
    rows = hazard_rows if hazard_rows is not None else load_mock_hazards()
    by_id = {city.id: city for city in catalog}
    graph = _drive_graph(road_edges)
    selected = _select_events(rows, catalog, graph, events)
    event_reports: list[dict[str, object]] = []
    for event in selected:
        event_reports.append(_score_event(event, catalog, road_edges, by_id, graph, routes_per_event))
    return _report(event_reports)


def load_saved_report(path: Path | None = None) -> dict[str, object]:
    """Read the JSON report written by scripts/backtest.py."""
    source = path or REPORT_PATH
    if not source.is_file():
        raise FileNotFoundError(source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("backtest report must be a JSON object")
    return payload


def write_report(report: dict[str, object], path: Path = REPORT_PATH) -> Path:
    """Save the report as JSON for the API and the backtest page."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def format_table(report: dict[str, object]) -> str:
    """Plain-text summary. Wording stays limited to the historical sample."""
    headers = ("Event", "As of", "Through danger", "Avoided", "Avg extra hours")
    rows = [
        (
            str(event["event_name"]),
            str(event["as_of"])[:10],
            str(event["routes_through_danger"]),
            str(event["routes_avoided"]),
            _hours(event["average_extra_hours"]),
        )
        for event in report["events"]
    ]
    rows.append(
        (
            "Total",
            "",
            str(report["routes_through_danger"]),
            str(report["routes_avoided"]),
            _hours(report["average_extra_hours"]),
        )
    )
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = [
        "Historical replay (not a forecast)",
        DISCLAIMER,
        "",
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
    ]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    lines.append("")
    lines.append(
        f"Events tested: {report['events_tested']}. "
        f"Routes through the later danger zone: {report['routes_through_danger']}. "
        f"Proposed routes that left those cities: {report['routes_avoided']}. "
        f"Average extra drive hours on the routes that left them: {_hours(report['average_extra_hours'])}."
    )
    return "\n".join(lines)


def _score_event(
    event: dict[str, object],
    cities: list[City],
    edges: list[Hop],
    by_id: dict[str, City],
    graph: nx.Graph,
    routes_per_event: int,
) -> dict[str, object]:
    start = _as_utc(event["start_time"])
    as_of = start - timedelta(days=OFFSET_DAYS)
    _assert_event_hidden(event, as_of)
    affected = affected_cities(event, cities)
    affected_ids = {city.id for city in affected}
    pairs = through_pairs(graph, by_id, affected_ids, routes_per_event)
    samples: list[dict[str, object]] = []
    for origin, dest, _path in pairs:
        ranked = plan_routes(
            cities,
            edges,
            f"{origin.name}, {origin.state}",
            f"{dest.name}, {dest.state}",
            as_of=as_of,
            deadline_hours=DEADLINE_HOURS,
        )
        samples.append(_sample(ranked, origin, dest, affected_ids, as_of))
    avoided = [sample for sample in samples if sample["avoided"]]
    extra = [float(sample["extra_drive_hours"]) for sample in avoided]
    return {
        "event_id": event["event_id"],
        "event_name": event.get("event_name") or event["event_id"],
        "event_start": start.isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "affected_cities": [f"{city.name}, {city.state}" for city in affected],
        "routes_tested": len(samples),
        "routes_through_danger": sum(1 for sample in samples if sample["through_danger"]),
        "routes_avoided": len(avoided),
        "average_extra_hours": _mean(extra),
        "samples": samples,
    }


def _sample(
    ranked: RankedRoutes,
    origin: City,
    dest: City,
    affected_ids: set[str],
    as_of: datetime,
) -> dict[str, object]:
    baseline_ids = [city.id for city in ranked.baseline.cities]
    proposed = ranked.routes[0]
    proposed_ids = [city.id for city in proposed.cities]
    through = bool(affected_ids.intersection(baseline_ids[1:-1]))
    left = route_avoided(baseline_ids, proposed_ids, affected_ids)
    as_of_day = as_of.astimezone(UTC).date()
    return {
        "start": f"{origin.name}, {origin.state}",
        "end": f"{dest.name}, {dest.state}",
        "as_of_date": as_of_day.isoformat(),
        "deadline_date": (as_of_day + timedelta(days=4)).isoformat(),
        "baseline_cities": [city.name for city in ranked.baseline.cities],
        "proposed_cities": [city.name for city in proposed.cities],
        "through_danger": through,
        "avoided": left,
        "extra_drive_hours": proposed.extra_drive_hours,
    }


def _select_events(
    rows: list[dict[str, object]],
    cities: list[City],
    graph: nx.Graph,
    limit: int,
) -> list[dict[str, object]]:
    by_id = {city.id: city for city in cities}
    ranked: list[tuple[int, str, datetime, str, dict[str, object]]] = []
    for event in rows:
        if "lat" not in event or "lon" not in event or "start_time" not in event:
            continue
        affected = affected_cities(event, cities)
        if not affected:
            continue
        affected_ids = {city.id for city in affected}
        if not through_pairs(graph, by_id, affected_ids, 1):
            continue
        start = _as_utc(event["start_time"])
        alert = str(event.get("alert_level") or "").casefold()
        primary = affected[0].id
        ranked.append((ALERT_RANK.get(alert, 9), primary, start, str(event.get("event_id")), event))
    ranked.sort(key=lambda item: (item[0], item[2], item[3]))
    chosen: list[dict[str, object]] = []
    seen_cities: set[str] = set()
    for _rank, primary, _start, _event_id, event in ranked:
        if primary in seen_cities:
            continue
        seen_cities.add(primary)
        chosen.append(event)
        if len(chosen) == limit:
            return chosen
    for _rank, _primary, _start, _event_id, event in ranked:
        if event in chosen:
            continue
        chosen.append(event)
        if len(chosen) == limit:
            break
    if len(chosen) < limit:
        raise ValueError(
            f"found {len(chosen)} disasters with a through-route; requested {limit}"
        )
    return chosen[:limit]


def _assert_event_hidden(event: dict[str, object], as_of: datetime) -> None:
    lat = float(event["lat"])
    lon = float(event["lon"])
    visible = get_hazard_events((lat - 2, lon - 2, lat + 2, lon + 2), as_of, 60)
    ids = {item["event_id"] for item in visible}
    if event["event_id"] in ids:
        raise RuntimeError(
            f"{event['event_id']} is visible at {as_of.isoformat()}, so this replay would use the event itself"
        )


def _report(events: list[dict[str, object]]) -> dict[str, object]:
    samples = [sample for event in events for sample in event["samples"]]
    avoided = [sample for sample in samples if sample["avoided"]]
    extra = [float(sample["extra_drive_hours"]) for sample in avoided]
    return {
        "disclaimer": DISCLAIMER,
        "as_of_offset_days": OFFSET_DAYS,
        "events_tested": len(events),
        "routes_tested": len(samples),
        "routes_through_danger": sum(1 for sample in samples if sample["through_danger"]),
        "routes_avoided": len(avoided),
        "average_extra_hours": _mean(extra),
        "events": events,
    }


def _drive_graph(edges: list[Hop]) -> nx.Graph:
    graph = nx.Graph()
    for edge in edges:
        graph.add_edge(edge.origin_id, edge.dest_id, weight=edge.drive_hours)
    return graph


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _hours(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.1f}"


def _as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip().strip('"').replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
