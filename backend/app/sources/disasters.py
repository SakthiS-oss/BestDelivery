"""Disaster records visible at as_of, from mock files or Snowflake."""

from datetime import datetime

from app.config import Settings
from app.domain.models import DisasterEvent


def fetch_disasters(
    settings: Settings,
    *,
    as_of: datetime,
    states: list[str],
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> list[DisasterEvent]:
    """Load hazards already known at as_of inside the bounding box."""
    raise NotImplementedError
