"""Reads and writes a trip's structured search brief.

Small on purpose. It exists so that the planning path, the search path and the
preferences endpoint all write the same row the same way, rather than three
places each mapping a slightly different subset of fields.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import TripNotFound
from app.db.models import Trip, TripPreference
from app.db.repositories import PreferenceRepository
from app.schemas.preferences import TripPreferenceIn, TripPreferenceOut


class PreferenceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.preferences = PreferenceRepository(session)

    def get(self, trip_id: str) -> TripPreferenceOut | None:
        record = self.preferences.get(trip_id)
        return to_out(record) if record else None

    def get_or_default(self, trip: Trip) -> TripPreferenceOut:
        """The brief for a trip, derived from the trip itself when absent.

        A journey planned before this feature existed still has a party size,
        interests and a hotel preference on its own row, so it gets a coherent
        brief rather than an empty one.
        """
        existing = self.get(trip.id)
        if existing is not None:
            return existing
        return TripPreferenceOut(
            trip_id=trip.id,
            adults=max(int(trip.travelers or 1), 1),
            children=0,
            interests=list(trip.interests or []),
            accommodation_type=_accommodation_from(trip.hotel_preference),
            notes=trip.additional_instructions,
            accessibility_requirements=trip.special_requirements,
            travelers_total=max(int(trip.travelers or 1), 1),
        )

    def upsert(self, trip_id: str, payload: TripPreferenceIn) -> TripPreferenceOut:
        trip = self.session.get(Trip, trip_id)
        if trip is None:
            raise TripNotFound(f"trip {trip_id} does not exist")

        record = self.preferences.upsert(
            trip_id,
            adults=payload.adults,
            children=payload.children,
            child_ages=list(payload.child_ages),
            flexible_days=payload.flexible_days,
            flexible_destination=payload.flexible_destination,
            cabin_class=payload.cabin_class,
            max_stops=payload.max_stops,
            baggage=payload.baggage,
            preferred_airlines=list(payload.preferred_airlines),
            excluded_airlines=list(payload.excluded_airlines),
            earliest_departure_hour=payload.earliest_departure_hour,
            latest_arrival_hour=payload.latest_arrival_hour,
            accommodation_type=payload.accommodation_type,
            hotel_min_rating=payload.hotel_min_rating,
            pace=payload.pace,
            interests=list(payload.interests),
            dietary_requirements=payload.dietary_requirements,
            accessibility_requirements=payload.accessibility_requirements,
            notes=payload.notes,
        )
        # The trip's own party size follows the brief, so history rows and the
        # journey header cannot disagree with the search that produced them.
        trip.travelers = payload.travelers
        self.session.flush()
        return to_out(record)


def to_out(record: TripPreference) -> TripPreferenceOut:
    return TripPreferenceOut(
        trip_id=record.trip_id,
        adults=record.adults,
        children=record.children,
        child_ages=list(record.child_ages or []),
        flexible_days=record.flexible_days,
        flexible_destination=bool(record.flexible_destination),
        cabin_class=record.cabin_class,
        max_stops=record.max_stops,
        baggage=record.baggage,
        preferred_airlines=list(record.preferred_airlines or []),
        excluded_airlines=list(record.excluded_airlines or []),
        earliest_departure_hour=record.earliest_departure_hour,
        latest_arrival_hour=record.latest_arrival_hour,
        accommodation_type=record.accommodation_type,
        hotel_min_rating=record.hotel_min_rating,
        pace=record.pace,
        interests=list(record.interests or []),
        dietary_requirements=record.dietary_requirements,
        accessibility_requirements=record.accessibility_requirements,
        notes=record.notes,
        travelers_total=record.travelers,
        updated_at=record.updated_at,
    )


def _accommodation_from(hotel_preference: str | None) -> str:
    """Map the older free-form hotel preference onto the new vocabulary."""
    mapping = {
        "hostel": "hostel",
        "guesthouse": "guesthouse",
        "apartment": "apartment",
        "resort": "resort",
        "three_star": "hotel",
        "four_star": "hotel",
        "five_star": "hotel",
    }
    return mapping.get(hotel_preference or "", "any")
