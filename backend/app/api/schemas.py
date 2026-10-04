"""Request and response bodies for the route planner API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from explain import RouteExplanation
from scoring import RankedRoutes

PLAN_EXAMPLE = {
    "start": "Dallas, TX",
    "end": "Atlanta, GA",
    "deadline": 72,
    "as_of_date": "2026-06-15",
}


class PlanRequest(BaseModel):
    """Start city, end city, a deadline, and an optional replay date."""

    model_config = ConfigDict(json_schema_extra={"example": PLAN_EXAMPLE})

    start: str = Field(min_length=1, description="Catalog city, as 'Dallas' or 'Dallas, TX'.", examples=["Dallas, TX"])
    end: str = Field(min_length=1, description="Catalog city, as 'Atlanta' or 'Atlanta, GA'.", examples=["Atlanta, GA"])
    deadline: float | datetime = Field(
        description="Hours from as_of_date until the delivery deadline, or an ISO-8601 timestamp after that instant.",
        examples=[72],
    )
    as_of_date: date | datetime | None = Field(
        default=None,
        description="Replay clock. A calendar date means the end of that UTC day. Defaults to now.",
        examples=["2026-06-15"],
    )

    @field_validator("start", "end")
    @classmethod
    def city_not_blank(cls, value: str) -> str:
        text = " ".join(value.split())
        if not text:
            raise ValueError("city name is empty")
        return text

    @field_validator("as_of_date", mode="before")
    @classmethod
    def parse_as_of(cls, value: object) -> date | datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise ValueError("as_of_date must be an ISO-8601 date or datetime")
        text = value.strip()
        if not text:
            return None
        try:
            if "T" not in text and " " not in text:
                return date.fromisoformat(text)
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("as_of_date must be an ISO-8601 date or datetime") from exc

    @field_validator("deadline")
    @classmethod
    def deadline_is_usable(cls, value: float | datetime) -> float | datetime:
        if isinstance(value, datetime):
            return value
        if value <= 0:
            raise ValueError("deadline must be a positive number of hours")
        return value


class PlanResponse(RankedRoutes):
    """Ranked routes, grounded explanations, and any omitted sources."""

    warnings: list[str] = Field(default_factory=list)
    explanations: list[RouteExplanation] = Field(default_factory=list)
    recommendation: str = ""
    explanation_source: Literal["model", "template"] = "template"


class CityOption(BaseModel):
    """One catalog city for the autocomplete list."""

    id: str
    name: str
    state: str
    label: str
    lat: float
    lon: float


class CityRiskResponse(BaseModel):
    """Hazard events and news articles for one city at as_of_date."""

    city: CityOption
    as_of_date: datetime
    hazard: dict[str, object]
    news: dict[str, object]
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Process status, mock mode, and whether Snowflake and Ollama answered."""

    status: str
    use_mock_data: bool
    snowflake: str = "unknown"
    ollama: str = "unknown"


__all__ = [
    "PLAN_EXAMPLE",
    "CityOption",
    "CityRiskResponse",
    "HealthResponse",
    "PlanRequest",
    "PlanResponse",
]
