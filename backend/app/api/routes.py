"""HTTP handlers. The plan route stays unimplemented until the pipeline step."""

from fastapi import APIRouter

from app.api.schemas import HealthResponse, PlanRequest, PlanResponse
from snowflake_client import health_check

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report process status, mock mode, and whether Snowflake answered SELECT 1."""
    report = health_check()
    return HealthResponse(
        status=str(report["status"]),
        use_mock_data=bool(report["use_mock_data"]),
        snowflake=str(report["snowflake"]),
    )


@router.post("/plan", response_model=PlanResponse)
def plan(body: PlanRequest) -> PlanResponse:
    """Rank candidate delivery routes for the given deadline."""
    raise NotImplementedError
