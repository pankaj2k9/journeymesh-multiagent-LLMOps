"""PostgreSQL-shaped persistence, exercised against the ephemeral fallback."""

from __future__ import annotations

import pytest

from app.db.database import backend_name, session_scope
from app.db.repositories import (
    AuditRepository,
    ConversationRepository,
    ReviewRepository,
    TripRepository,
)
from app.services.travel_service import TravelService


def test_the_database_backend_is_reported(client):
    assert backend_name() in {"postgresql", "ephemeral_sqlite"}


@pytest.mark.asyncio
async def test_planning_persists_the_trip_its_results_and_its_review(family_request):
    with session_scope() as session:
        service = TravelService(session)
        response = await service.plan(family_request)
        trip_id = response.trip_id  # type: ignore[union-attr]

    with session_scope() as session:
        trips = TripRepository(session)
        trip = trips.get(trip_id)
        assert trip is not None
        assert trip.destination == "Singapore"
        assert trip.travelers == 3
        assert trip.interests == ["food", "nature", "family_activities"]
        assert trip.preferred_language == "en"

        result = trips.get_result(trip_id)
        assert result is not None
        assert result.itinerary["days"]
        assert result.budget_analysis["breakdown"]
        assert result.evaluation_summary["overall_score"] > 0
        assert result.provider_metadata

        reviews = ReviewRepository(session).list_for_trip(trip_id)
        assert reviews and reviews[0].revision_number == 1


@pytest.mark.asyncio
async def test_conversation_messages_are_stored_without_model_reasoning(family_request):
    with session_scope() as session:
        service = TravelService(session)
        response = await service.plan(family_request)
        trip_id = response.trip_id  # type: ignore[union-attr]

    with session_scope() as session:
        messages = ConversationRepository(session).list_for_trip(trip_id)
        assert messages
        roles = {message.role for message in messages}
        assert "user" in roles
        blob = " ".join(message.content for message in messages).lower()
        assert "chain of thought" not in blob


@pytest.mark.asyncio
async def test_audit_events_are_recorded_for_a_planned_trip(family_request):
    with session_scope() as session:
        service = TravelService(session)
        response = await service.plan(family_request)
        trip_id = response.trip_id  # type: ignore[union-attr]

    with session_scope() as session:
        events = AuditRepository(session).list_for_trip(trip_id)
        assert any(event.event_type == "TRIP_PLANNED" for event in events)


@pytest.mark.asyncio
async def test_deleting_a_trip_removes_its_children(family_request):
    with session_scope() as session:
        service = TravelService(session)
        response = await service.plan(family_request)
        trip_id = response.trip_id  # type: ignore[union-attr]

    with session_scope() as session:
        service = TravelService(session)
        service.delete(trip_id)

    with session_scope() as session:
        trips = TripRepository(session)
        assert trips.get(trip_id) is None
        assert trips.get_result(trip_id) is None
        assert ReviewRepository(session).list_for_trip(trip_id) == []


def test_repository_listing_is_paginated_and_scoped():
    from app.db.models import Trip

    with session_scope() as session:
        repo = TripRepository(session)
        for index in range(3):
            repo.create(
                id=f"trip-{index}",
                session_id="session-a" if index < 2 else "session-b",
                user_query="Plan a trip",
                destination="Rome",
            )

    with session_scope() as session:
        repo = TripRepository(session)
        assert repo.count() == 3
        assert repo.count(session_id="session-a") == 2
        assert len(repo.list(limit=2)) == 2
        assert all(isinstance(trip, Trip) for trip in repo.list())
