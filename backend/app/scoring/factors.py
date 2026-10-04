"""Named score terms and the risk-cost combination."""

from app.domain.models import Factor, FactorName


def make_factor(
    name: FactorName,
    value: float,
    unit: str,
    evidence_ids: list[str],
) -> Factor:
    """Assemble one factor row from values the caller already computed."""
    raise NotImplementedError


def risk_cost_hours(
    *,
    hazard_risk: float,
    news_risk: float,
    delay_hours: float,
    hazard_weight_hours: float,
    news_weight_hours: float,
) -> float:
    """Combine the three risk inputs and the configured weights into hours."""
    raise NotImplementedError
