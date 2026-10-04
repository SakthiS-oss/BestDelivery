"""HTTP handlers for planning, the city catalog, city risk, and health."""

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query

from app.api.schemas import (
    PLAN_EXAMPLE,
    CityOption,
    CityRiskResponse,
    HealthResponse,
    PlanRequest,
    PlanResponse,
)
from app.api.service import CatalogError, build_city_risk, build_health, build_plan, list_city_options

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report mock mode and whether Snowflake and Ollama are reachable."""
    return build_health()


@router.get("/cities", response_model=list[CityOption])
def cities() -> list[CityOption]:
    """Supported cities. Send ``label`` back as ``start`` or ``end`` on POST /plan."""
    try:
        return list_city_options()
    except CatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/city/{name}/risk", response_model=CityRiskResponse)
def city_risk(
    name: str,
    as_of_date: Annotated[
        str | None,
        Query(description="Replay date or timestamp. A date uses the end of that UTC day."),
    ] = None,
) -> CityRiskResponse:
    """Hazard events and news for one city. An unknown city is HTTP 400."""
    try:
        return build_city_risk(name, as_of_date)
    except CatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plan",
    response_model=PlanResponse,
    responses={
        400: {"description": "Unknown city, ambiguous city, or no road path.", "content": {"application/json": {"example": {"detail": "unknown city: Atlantis"}}}},
        504: {"description": "The request exceeded the server timeout.", "content": {"application/json": {"example": {"detail": "request timed out"}}}},
    },
)
def plan(
    body: Annotated[
        PlanRequest,
        Body(
            openapi_examples={
                "dallas_to_atlanta": {
                    "summary": "Dallas to Atlanta in 72 hours",
                    "description": "Ranks routes using hazards and news known at the end of as_of_date.",
                    "value": PLAN_EXAMPLE,
                }
            }
        ),
    ],
) -> PlanResponse:
    """Rank candidate routes. A down Snowflake or Ollama yields partial scores and ``warnings``."""
    try:
        return build_plan(body)
    except CatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
