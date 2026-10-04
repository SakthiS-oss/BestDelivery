"""HTTP handlers. Bodies stay unimplemented until the pipeline step."""

from fastapi import APIRouter

from app.api.schemas import HealthResponse, PlanRequest, PlanResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report process status and whether mock data is on."""
    raise NotImplementedError


@router.post("/plan", response_model=PlanResponse)
def plan(body: PlanRequest) -> PlanResponse:
    """Rank candidate delivery routes for the given deadline."""
    raise NotImplementedError
