"""Local JSON and CSV readers for USE_MOCK_DATA=true."""

from pathlib import Path


def load_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file into row dicts."""
    raise NotImplementedError


def load_json(path: Path) -> list[dict[str, object]]:
    """Read a JSON array file."""
    raise NotImplementedError
