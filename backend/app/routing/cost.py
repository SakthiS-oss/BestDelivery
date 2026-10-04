"""Pluggable edge weights. Risk is added later; the default penalty is zero."""

from collections.abc import Callable

RiskPenalty = Callable[[str, str], float]


def zero_risk_penalty(origin_id: str, dest_id: str) -> float:
    """Hours of risk added to one hop. Scoring will replace this."""
    return 0.0


def edge_cost(drive_hours: float, risk_penalty: float) -> float:
    """Combine driving time and a risk penalty into one edge weight."""
    return drive_hours + risk_penalty
