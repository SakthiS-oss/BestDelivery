"""Read-only Snowflake access. Credentials come from the environment."""

import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISASTER_TABLE = (
    "AMBEE_GLOBAL_NATURAL_DISASTERS_DATA_HISTORICAL_AND_PRESENT_CONDITIONS.ND.ND_ACTUALS"
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|COPY|PUT|GET|CALL|ALTER|DROP|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def use_mock_data() -> bool:
    """True when disasters should be read from local files instead of Snowflake."""
    _load_env()
    return os.environ.get("USE_MOCK_DATA", "true").strip().lower() in {"1", "true", "yes", "on"}


def qualified_table(name: str | None = None) -> str:
    """Return a dotted Snowflake name after checking each identifier."""
    _load_env()
    raw = (name or os.environ.get("SNOWFLAKE_DISASTER_TABLE") or DEFAULT_DISASTER_TABLE).strip()
    parts = raw.split(".")
    if not 1 <= len(parts) <= 3 or not all(_IDENTIFIER.fullmatch(part) for part in parts):
        raise ValueError(f"unsafe Snowflake table name: {raw}")
    return ".".join(parts)


def assert_select_only(sql: str) -> None:
    """Accept one read-only SELECT or WITH query. Reject every other statement."""
    text = _strip_comments(sql).strip().rstrip(";").strip()
    if not text or ";" in text:
        raise ValueError("only one read-only SELECT is allowed")
    head = text.split(None, 1)[0].upper()
    if head not in {"SELECT", "WITH"} or _FORBIDDEN.search(text):
        raise ValueError("only a read-only SELECT is allowed")


@contextmanager
def snowflake_connection() -> Iterator[object]:
    """Open a connector session and close it when the block ends."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def connect() -> object:
    """Open a Snowflake connection from SNOWFLAKE_* environment variables."""
    import snowflake.connector

    cfg = _config()
    missing = [key for key in ("account", "user", "password", "warehouse") if not cfg[key]]
    if missing:
        raise RuntimeError("missing Snowflake settings: " + ", ".join(missing))
    return snowflake.connector.connect(
        account=cfg["account"],
        user=cfg["user"],
        password=cfg["password"],
        warehouse=cfg["warehouse"],
        database=cfg["database"] or None,
        schema=cfg["schema"] or None,
        role=cfg["role"] or None,
        login_timeout=8,
        network_timeout=15,
    )


def fetch_all(sql: str, params: Mapping[str, object] | None = None) -> list[dict[str, object]]:
    """Run one parameterized SELECT and return row dicts with lowercase keys."""
    assert_select_only(sql)
    with snowflake_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, dict(params) if params else None)
            columns = [column[0].lower() for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        finally:
            cursor.close()


def health_check() -> dict[str, object]:
    """Confirm Snowflake with SELECT 1. Mock mode skips the network."""
    if use_mock_data():
        return {"status": "ok", "use_mock_data": True, "snowflake": "skipped"}
    try:
        rows = fetch_all("SELECT 1 AS ok", None)
    except Exception:
        return {"status": "degraded", "use_mock_data": False, "snowflake": "unavailable"}
    connected = bool(rows)
    return {
        "status": "ok" if connected else "degraded",
        "use_mock_data": False,
        "snowflake": "ok" if connected else "unavailable",
    }


def _load_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=False)


def _config() -> dict[str, str]:
    _load_env()
    return {
        "account": os.environ.get("SNOWFLAKE_ACCOUNT", "").strip(),
        "user": os.environ.get("SNOWFLAKE_USER", "").strip(),
        "password": os.environ.get("SNOWFLAKE_PASSWORD", "").strip(),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "").strip(),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "").strip(),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "").strip(),
        "role": os.environ.get("SNOWFLAKE_ROLE", "").strip(),
    }


def _strip_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", without_block)
