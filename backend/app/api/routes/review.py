"""Human-in-the-loop review endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import review_service
from app.schemas.review import (
    ApproveRequest,
    ApproveResponse,
    ChangeRequest,
    ChangeResponse,
)
from app.services.review_service import ReviewService

router = APIRouter(prefix="/trips", tags=["review"])


@router.post(
    "/{trip_id}/approve",
    response_model=ApproveResponse,
    summary="Approve a draft journey",
    description=(
        "Resumes the paused workflow. The Final Response Agent assembles the approved "
        "journey in the requested language and the result is persisted."
    ),
)
async def approve(
    trip_id: str,
    payload: ApproveRequest | None = None,
    service: ReviewService = Depends(review_service),
) -> ApproveResponse:
    payload = payload or ApproveRequest()
    return await service.approve(
        trip_id, response_language=payload.response_language, note=payload.reviewer_note
    )


@router.post(
    "/{trip_id}/request-changes",
    response_model=ChangeResponse,
    summary="Ask JourneyMesh to change something",
    description=(
        "The Supervisor reads the request, decides which agents it affects and re-runs "
        "only those agents plus the ones that depend on them. Everything else is kept."
    ),
)
async def request_changes(
    trip_id: str,
    payload: ChangeRequest,
    service: ReviewService = Depends(review_service),
) -> ChangeResponse:
    return await service.request_changes(
        trip_id,
        requested_changes=payload.requested_changes,
        response_language=payload.response_language,
    )


@router.post(
    "/{trip_id}/regenerate",
    response_model=ChangeResponse,
    summary="Regenerate the whole journey",
)
async def regenerate(
    trip_id: str,
    service: ReviewService = Depends(review_service),
) -> ChangeResponse:
    return await service.regenerate(trip_id)
