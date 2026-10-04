"""News records published at or before as_of."""

from datetime import datetime

from app.config import Settings
from app.domain.models import City, NewsItem


def fetch_news(
    settings: Settings,
    *,
    as_of: datetime,
    cities: list[City],
    lookback_days: float,
) -> list[NewsItem]:
    """Load news for these cities in the lookback window ending at as_of."""
    raise NotImplementedError
