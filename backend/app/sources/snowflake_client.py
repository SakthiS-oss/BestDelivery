"""Snowflake session helpers. SELECT-only, parameters bound by the connector."""

from collections.abc import Mapping

from app.config import Settings


def assert_select_only(sql: str) -> None:
    """Accept a single read-only SELECT. Reject every other statement."""
    raise NotImplementedError


def connect(settings: Settings) -> object:
    """Open a Snowflake connection. The object is a connector connection."""
    raise NotImplementedError


def fetch_all(
    conn: object,
    sql: str,
    params: Mapping[str, object],
) -> list[dict[str, object]]:
    """Run one parameterized SELECT and return row dicts."""
    raise NotImplementedError
