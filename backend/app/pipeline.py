"""Orchestrate routing, scoring, and explanation for one plan request."""

from app.api.schemas import PlanRequest, PlanResponse
from app.config import Settings


def build_plan(request: PlanRequest, settings: Settings) -> PlanResponse:
    """Resolve the deadline, score candidate routes, explain them, and rank."""
    raise NotImplementedError
