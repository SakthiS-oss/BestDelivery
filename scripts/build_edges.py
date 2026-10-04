#!/usr/bin/env python3
"""Write data/cities.csv and data/edges.csv from the catalog below.

Each city is linked to its nearest neighbors at 100–400 great-circle miles,
at most five of them. Stored road miles are that distance. Drive hours use 55 mph.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.routing.cities import city_id  # noqa: E402
from app.routing.distance import drive_hours, haversine_miles  # noqa: E402

MIN_MILES = 100.0
MAX_MILES = 400.0
NEIGHBORS = 5
AVG_MPH = 55.0

# name, state, lat, lon, population (2020 census, city proper)
CITIES: list[tuple[str, str, float, float, int]] = [
    ("Seattle", "WA", 47.6062, -122.3321, 737015),
    ("Portland", "OR", 45.5152, -122.6784, 652503),
    ("Spokane", "WA", 47.6588, -117.4260, 228989),
    ("Boise", "ID", 43.6150, -116.2023, 235684),
    ("Missoula", "MT", 46.8721, -113.9940, 75516),
    ("Billings", "MT", 45.7833, -108.5007, 117116),
    ("Bismarck", "ND", 46.8083, -100.7837, 73622),
    ("Redding", "CA", 40.5865, -122.3917, 93611),
    ("Sacramento", "CA", 38.5816, -121.4944, 524943),
    ("San Francisco", "CA", 37.7749, -122.4194, 873965),
    ("Fresno", "CA", 36.7378, -119.7871, 542107),
    ("Los Angeles", "CA", 34.0522, -118.2437, 3898747),
    ("San Diego", "CA", 32.7157, -117.1611, 1386932),
    ("Reno", "NV", 39.5296, -119.8138, 264165),
    ("Las Vegas", "NV", 36.1699, -115.1398, 641903),
    ("Salt Lake City", "UT", 40.7608, -111.8910, 199723),
    ("Phoenix", "AZ", 33.4484, -112.0740, 1608139),
    ("Tucson", "AZ", 32.2226, -110.9747, 542629),
    ("Denver", "CO", 39.7392, -104.9903, 715522),
    ("Albuquerque", "NM", 35.0844, -106.6504, 564559),
    ("El Paso", "TX", 31.7619, -106.4850, 678815),
    ("Amarillo", "TX", 35.2210, -101.8313, 200393),
    ("North Platte", "NE", 41.1239, -100.7654, 23390),
    ("Omaha", "NE", 41.2565, -95.9345, 486051),
    ("Wichita", "KS", 37.6872, -97.3301, 397532),
    ("Kansas City", "MO", 39.0997, -94.5786, 508090),
    ("Midland", "TX", 31.9973, -102.0779, 132524),
    ("Dallas", "TX", 32.7767, -96.7970, 1304379),
    ("Oklahoma City", "OK", 35.4676, -97.5164, 681054),
    ("Tulsa", "OK", 36.1540, -95.9928, 413066),
    ("Austin", "TX", 30.2672, -97.7431, 961855),
    ("San Antonio", "TX", 29.4241, -98.4936, 1434625),
    ("Houston", "TX", 29.7604, -95.3698, 2304580),
    ("Little Rock", "AR", 34.7465, -92.2896, 202591),
    ("New Orleans", "LA", 29.9511, -90.0715, 383997),
    ("Memphis", "TN", 35.1495, -90.0490, 633104),
    ("Des Moines", "IA", 41.5868, -93.6250, 214133),
    ("Minneapolis", "MN", 44.9778, -93.2650, 429954),
    ("Madison", "WI", 43.0731, -89.4012, 269840),
    ("Chicago", "IL", 41.8781, -87.6298, 2746388),
    ("St. Louis", "MO", 38.6270, -90.1994, 301578),
    ("Indianapolis", "IN", 39.7684, -86.1581, 887642),
    ("Detroit", "MI", 42.3314, -83.0458, 639111),
    ("Cincinnati", "OH", 39.1031, -84.5120, 309317),
    ("Columbus", "OH", 39.9612, -82.9988, 905748),
    ("Cleveland", "OH", 41.4993, -81.6944, 372624),
    ("Pittsburgh", "PA", 40.4406, -79.9959, 302971),
    ("Buffalo", "NY", 42.8864, -78.8784, 278349),
    ("Nashville", "TN", 36.1627, -86.7816, 689447),
    ("Atlanta", "GA", 33.7490, -84.3880, 498715),
    ("Birmingham", "AL", 33.5186, -86.8104, 200733),
    ("Mobile", "AL", 30.6954, -88.0399, 187041),
    ("Jacksonville", "FL", 30.3322, -81.6557, 949611),
    ("Orlando", "FL", 28.5383, -81.3792, 307573),
    ("Tampa", "FL", 27.9506, -82.4572, 384959),
    ("Miami", "FL", 25.7617, -80.1918, 442241),
    ("Charlotte", "NC", 35.2271, -80.8431, 874579),
    ("Raleigh", "NC", 35.7796, -78.6382, 467665),
    ("Richmond", "VA", 37.5407, -77.4360, 226610),
    ("Washington", "DC", 38.9072, -77.0369, 689545),
    ("Philadelphia", "PA", 39.9526, -75.1652, 1603797),
    ("New York", "NY", 40.7128, -74.0060, 8804190),
    ("Boston", "MA", 42.3601, -71.0589, 675647),
]


def _rows() -> list[dict[str, str | float | int]]:
    rows = []
    for name, state, lat, lon, population in CITIES:
        rows.append(
            {
                "id": city_id(name, state),
                "name": name,
                "state": state,
                "lat": lat,
                "lon": lon,
                "population": population,
            }
        )
    return rows


def _edges(rows: list[dict[str, str | float | int]]) -> list[tuple[dict, dict, float]]:
    chosen: set[tuple[str, str]] = set()
    edges: list[tuple[dict, dict, float]] = []
    for city in rows:
        ranked: list[tuple[float, dict]] = []
        for other in rows:
            if other["id"] == city["id"]:
                continue
            miles = haversine_miles(float(city["lat"]), float(city["lon"]), float(other["lat"]), float(other["lon"]))
            if MIN_MILES <= miles <= MAX_MILES:
                ranked.append((miles, other))
        ranked.sort(key=lambda item: (item[0], str(item[1]["id"])))
        for miles, other in ranked[:NEIGHBORS]:
            key = tuple(sorted((str(city["id"]), str(other["id"]))))
            if key in chosen:
                continue
            chosen.add(key)
            left, right = (city, other) if key[0] == city["id"] else (other, city)
            edges.append((left, right, miles))
    edges.sort(key=lambda item: (str(item[0]["name"]), str(item[0]["state"]), str(item[1]["name"])))
    return edges


def _components(rows: list[dict], edges: list[tuple[dict, dict, float]]) -> list[set[str]]:
    neighbors: dict[str, set[str]] = {str(row["id"]): set() for row in rows}
    for left, right, _miles in edges:
        neighbors[str(left["id"])].add(str(right["id"]))
        neighbors[str(right["id"])].add(str(left["id"]))
    seen: set[str] = set()
    components: list[set[str]] = []
    for node in neighbors:
        if node in seen:
            continue
        stack = [node]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(neighbors[current] - component)
        seen.update(component)
        components.append(component)
    return components


def main() -> None:
    rows = _rows()
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate city id")
    edges = _edges(rows)
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    with (data / "cities.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "state", "lat", "lon", "population"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "name": row["name"],
                    "state": row["state"],
                    "lat": f"{float(row['lat']):.4f}",
                    "lon": f"{float(row['lon']):.4f}",
                    "population": row["population"],
                }
            )
    with (data / "edges.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["from_city", "from_state", "to_city", "to_state", "road_miles", "typical_drive_hours"],
        )
        writer.writeheader()
        for left, right, miles in edges:
            writer.writerow(
                {
                    "from_city": left["name"],
                    "from_state": left["state"],
                    "to_city": right["name"],
                    "to_state": right["state"],
                    "road_miles": f"{miles:.1f}",
                    "typical_drive_hours": f"{drive_hours(miles, avg_speed_mph=AVG_MPH):.2f}",
                }
            )

    components = _components(rows, edges)
    degree: dict[str, int] = {str(row["id"]): 0 for row in rows}
    for left, right, _miles in edges:
        degree[str(left["id"])] += 1
        degree[str(right["id"])] += 1
    thin = [row for row in rows if degree[str(row["id"])] < 3]
    print(f"cities={len(rows)} edges={len(edges)} components={len(components)}")
    if thin:
        print("fewer than 3 neighbors:")
        for row in thin:
            print(f"  {row['name']}, {row['state']} degree={degree[str(row['id'])]}")
    if len(components) != 1:
        by_id = {str(row["id"]): row for row in rows}
        print("graph is disconnected")
        for component in components:
            names = sorted(f"{by_id[node]['name']}, {by_id[node]['state']}" for node in component)
            print(f"  ({len(names)}) {', '.join(names[:8])}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
