"""Deadline resolution and arrival checks. All clocks are UTC."""

from datetime import datetime


def resolve_deadline(
    *,
    as_of: datetime,
    deadline_at: datetime | None,
    deadline_days: float | None,
) -> datetime:
    """Turn an absolute timestamp or a day count into one deadline."""
    raise NotImplementedError


def arrival_time(as_of: datetime, travel_hours: float, delay_hours: float) -> datetime:
    """Departure as_of plus computed driving hours and hazard delay."""
    raise NotImplementedError


def meets_deadline(eta: datetime, deadline_at: datetime) -> bool:
    """True when arrival is at or before the deadline."""
    raise NotImplementedError


def slack_hours(eta: datetime, deadline_at: datetime) -> float:
    """Hours between arrival and the deadline. Negative means late."""
    raise NotImplementedError
