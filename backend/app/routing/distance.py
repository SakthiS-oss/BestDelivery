"""Pure distance and drive-time helpers."""

import math

EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return EARTH_RADIUS_MILES * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def road_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    road_factor: float,
) -> float:
    """Approximate driving miles from the great-circle distance."""
    if road_factor <= 0:
        raise ValueError("road_factor must be positive")
    return haversine_miles(lat1, lon1, lat2, lon2) * road_factor


def drive_hours(miles: float, *, avg_speed_mph: float) -> float:
    """Hours on the road at a constant speed, before hazard delay."""
    if avg_speed_mph <= 0:
        raise ValueError("avg_speed_mph must be positive")
    if miles < 0:
        raise ValueError("miles must be non-negative")
    return miles / avg_speed_mph
