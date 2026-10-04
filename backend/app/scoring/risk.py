"""Per-route scores from disasters, news, and drive time."""

from datetime import datetime

from app.config import Settings
from app.domain.models import DisasterEvent, NewsItem, Route, RouteScore


def score_route(
    route: Route,
    disasters: list[DisasterEvent],
    news: list[NewsItem],
    *,
    as_of: datetime,
    deadline_at: datetime,
    settings: Settings,
) -> RouteScore:
    """Fill every named factor and the deadline flag for one route."""
    raise NotImplementedError
