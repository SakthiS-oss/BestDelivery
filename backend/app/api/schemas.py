"""Request and response bodies for /api/plan."""

from datetime import datetime

from pydantic import BaseModel

from app.domain.models import ExplainedRoute


class PlanRequest(BaseModel):
    """Start, end, a deadline, and the replay instant."""

    start_city: str
    end_city: str
    deadline_at: datetime | None = None
    deadline_days: float | None = None
    as_of: datetime


class PlanResponse(BaseModel):
    """Ranked routes, each with factors, a deadline flag, and an explanation."""

    as_of: datetime
    deadline_at: datetime
    routes: list[ExplainedRoute]


class HealthResponse(BaseModel):
    """Process liveness, the mock-data switch, and Snowflake connectivity."""

    status: str
    use_mock_data: bool
    snowflake: str = "unknown"
