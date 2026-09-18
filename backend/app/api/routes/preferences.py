"""The structured search brief for one journey."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import db_session
from app.core.exceptions import TripNotFound
from app.db.models import Trip
from app.schemas.preferences import TripPreferenceIn, TripPreferenceOut
from app.services.preference_service import PreferenceService

router = APIRouter(prefix="/trips", tags=["preferences"])


def preference_service(session=Depends(db_session)) -> PreferenceService:  # noqa: ANN001
    return PreferenceService(session)


@router.get(
    "/{trip_id}/preferences",
    response_model=TripPreferenceOut,
    summary="Read the search brief",
    description=(
        "A journey planned before preferences existed gets a brief derived from its "
        "own row rather than an empty one."
    ),
)
def read_preferences(
    trip_id: str,
    service: PreferenceService = Depends(preference_service),
    session=Depends(db_session),  # noqa: ANN001
) -> TripPreferenceOut:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise TripNotFound(f"trip {trip_id} does not exist")
    return service.get_or_default(trip)


@router.put(
    "/{trip_id}/preferences",
    response_model=TripPreferenceOut,
    summary="Replace the search brief",
)
def write_preferences(
    trip_id: str,
    payload: TripPreferenceIn,
    service: PreferenceService = Depends(preference_service),
) -> TripPreferenceOut:
    return service.upsert(trip_id, payload)
