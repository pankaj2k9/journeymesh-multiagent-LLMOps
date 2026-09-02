"""Trip planning endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import request_id, travel_service
from app.schemas.travel import (
    GuardrailBlockedResponse,
    TripPlanRequest,
    TripPlanResponse,
)
from app.services.travel_service import TravelService

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post(
    "/plan",
    response_model=TripPlanResponse | GuardrailBlockedResponse,
    summary="Plan a journey",
    description=(
        "Runs the input guardrails, lets the Supervisor choose the specialist agents "
        "and returns a draft journey that is waiting for human review. A request that "
        "the guardrails reject returns a safe `status: blocked` payload rather than an "
        "error, so the interface can explain what happened."
    ),
)
async def plan_trip(
    payload: TripPlanRequest,
    service: TravelService = Depends(travel_service),
    rid: str | None = Depends(request_id),
) -> TripPlanResponse | GuardrailBlockedResponse:
    return await service.plan(payload, request_id=rid)
