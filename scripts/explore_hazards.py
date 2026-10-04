"""Print hazard counts by event type and year.

Uses data/mock_hazards.json when USE_MOCK_DATA is true (the default).
Set USE_MOCK_DATA=false to aggregate the Snowflake ND_ACTUALS table.
"""

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from hazards import load_mock_hazards  # noqa: E402
from snowflake_client import fetch_all, qualified_table, use_mock_data  # noqa: E402


def main() -> None:
    if use_mock_data():
        _print_mock()
        print("Mock mode. Set USE_MOCK_DATA=false to query Snowflake.")
        return
    table = qualified_table()
    rows = fetch_all(
        f"""
        SELECT
            event_type,
            YEAR(TRY_TO_TIMESTAMP_NTZ(TO_VARCHAR(date))) AS event_year,
            COUNT(*) AS event_count
        FROM {table}
        GROUP BY event_type, event_year
        ORDER BY event_year, event_type
        """,
        None,
    )
    print(f"table: {table}")
    print(f"{'year':<8}{'event_type':<24}{'count':>10}")
    for row in rows:
        year = row.get("event_year")
        print(f"{str(year or ''):<8}{str(row.get('event_type') or ''):<24}{int(row['event_count']):>10}")


def _print_mock() -> None:
    events = load_mock_hazards()
    by_type: Counter[str] = Counter(str(event["event_type"]) for event in events)
    by_year: Counter[int] = Counter()
    for event in events:
        start = event["start_time"]
        if isinstance(start, datetime):
            by_year[start.year] += 1
    print(f"mock events: {len(events)}")
    print("by type:")
    for name, count in sorted(by_type.items()):
        print(f"  {name}: {count}")
    print("by year:")
    for year, count in sorted(by_year.items()):
        print(f"  {year}: {count}")


if __name__ == "__main__":
    main()
