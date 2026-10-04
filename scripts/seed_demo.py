#!/usr/bin/env python3
"""Confirm the local demo files, and build the road catalog if it is missing.

Mock mode reads data/cities.csv, data/edges.csv, data/mock_hazards.json, and
data/mock_news.json. This script does not overwrite a file that is already there.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CITIES = ROOT / "data" / "cities.csv"
EDGES = ROOT / "data" / "edges.csv"
HAZARDS = ROOT / "data" / "mock_hazards.json"
NEWS = ROOT / "data" / "mock_news.json"


def main() -> int:
    built = False
    if not CITIES.is_file() or not EDGES.is_file():
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_edges.py")])
        built = True
    cities = _csv_rows(CITIES)
    edges = _csv_rows(EDGES)
    hazards = _json_list(HAZARDS)
    articles = _json_list(NEWS)
    if not cities or not edges or not hazards or not articles:
        print("Demo data is incomplete.", file=sys.stderr)
        return 1
    action = "Built" if built else "Found"
    print(
        f"{action} {len(cities)} cities, {len(edges)} road hops, "
        f"{len(hazards)} hazard events, {len(articles)} news articles."
    )
    return 0


def _csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        print(f"Missing {path.relative_to(ROOT)}", file=sys.stderr)
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json_list(path: Path) -> list[object]:
    if not path.is_file():
        print(f"Missing {path.relative_to(ROOT)}", file=sys.stderr)
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"{path.relative_to(ROOT)} is not valid JSON.", file=sys.stderr)
        return []
    if not isinstance(payload, list):
        print(f"{path.relative_to(ROOT)} must be a JSON array.", file=sys.stderr)
        return []
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
