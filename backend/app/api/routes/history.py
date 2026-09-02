"""Journey history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import session_header, travel_service
from app.schemas.travel import DeleteResponse, TripDetailResponse, TripListResponse
from app.services.travel_service import TravelService

router = APIRouter(prefix="/trips", tags=["history"])


@router.get("", response_model=TripListResponse, summary="List previous journeys")
def list_trips(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, max_length=32),
    service: TravelService = Depends(travel_service),
    session_id: str | None = Depends(session_header),
) -> TripListResponse:
    return service.list(limit=limit, offset=offset, session_id=session_id, status=status)


@router.get("/{trip_id}", response_model=TripDetailResponse, summary="Read one journey")
def get_trip(
    trip_id: str,
    service: TravelService = Depends(travel_service),
) -> TripDetailResponse:
    return service.get(trip_id)


@router.delete("/{trip_id}", response_model=DeleteResponse, summary="Delete a journey")
def delete_trip(
    trip_id: str,
    service: TravelService = Depends(travel_service),
) -> DeleteResponse:
    service.delete(trip_id)
    return DeleteResponse(trip_id=trip_id, deleted=True)
