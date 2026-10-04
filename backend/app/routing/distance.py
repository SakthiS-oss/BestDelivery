"""Pure distance and drive-time helpers."""


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles."""
    raise NotImplementedError


def road_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    road_factor: float,
) -> float:
    """Approximate driving miles from the great-circle distance."""
    raise NotImplementedError


def drive_hours(miles: float, *, avg_speed_mph: float) -> float:
    """Hours on the road at a constant speed, before hazard delay."""
    raise NotImplementedError
