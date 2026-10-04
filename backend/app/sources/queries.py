"""Parameterized SELECT text. Table names are not user input."""


def disasters_sql() -> str:
    """Return the read-only disaster query. Filters are bound parameters."""
    raise NotImplementedError


def news_sql() -> str:
    """Return the read-only news query. Filters are bound parameters."""
    raise NotImplementedError
