"""Order routes by combined travel and risk cost."""

from app.domain.models import RouteResult


def rank_by_total_cost(results: list[RouteResult]) -> list[RouteResult]:
    """Sort by total_cost_hours ascending. Ties keep input order."""
    raise NotImplementedError
