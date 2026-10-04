"""Deadline checks. All clocks are UTC."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ItineraryEstimate:
    """Drive time, required overnight rest, and whether the deadline holds."""

    drive_hours: float
    overnight_stops: int
    rest_hours: float
    elapsed_hours: float
    deadline_hours: float
    meets_deadline: bool


def estimate_itinerary(
    drive_hours: float,
    deadline_hours: float,
    *,
    max_drive_hours_per_day: float = 10.0,
    rest_hours_per_stop: float = 8.0,
) -> ItineraryEstimate:
    """Add overnight rest after each 10-hour driving day and compare with the deadline."""
    if drive_hours < 0:
        raise ValueError("drive_hours must be non-negative")
    if max_drive_hours_per_day <= 0:
        raise ValueError("max_drive_hours_per_day must be positive")
    if rest_hours_per_stop < 0:
        raise ValueError("rest_hours_per_stop must be non-negative")
    measured = round(drive_hours, 4)
    if measured <= max_drive_hours_per_day:
        stops = 0
    else:
        driving_days = math.ceil(round(measured / max_drive_hours_per_day, 6))
        stops = driving_days - 1
    rest = stops * rest_hours_per_stop
    elapsed = drive_hours + rest
    return ItineraryEstimate(
        drive_hours=drive_hours,
        overnight_stops=stops,
        rest_hours=rest,
        elapsed_hours=elapsed,
        deadline_hours=deadline_hours,
        meets_deadline=elapsed <= deadline_hours,
    )
