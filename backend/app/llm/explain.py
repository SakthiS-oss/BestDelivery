"""Turn a scored route into plain-language text that cites its inputs."""

from datetime import datetime

from app.config import Settings
from app.domain.models import Citation, DisasterEvent, NewsItem, Route, RouteScore


def build_citations(
    route: Route,
    score: RouteScore,
    disasters: list[DisasterEvent],
    news: list[NewsItem],
) -> list[Citation]:
    """List the only numbers, cities, and events an explanation may mention."""
    raise NotImplementedError


def explain_route(
    route: Route,
    score: RouteScore,
    disasters: list[DisasterEvent],
    news: list[NewsItem],
    *,
    as_of: datetime,
    settings: Settings,
) -> tuple[str, list[Citation]]:
    """Explain one scored route as of the given instant."""
    raise NotImplementedError


def assert_explanation_grounded(text: str, citations: list[Citation]) -> None:
    """Require the text to stick to cities, numbers, and record ids in citations."""
    raise NotImplementedError
