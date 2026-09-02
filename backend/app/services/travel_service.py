"""Travel planning service.

Sits between the API layer and the graph: runs the input guardrails, drives
the workflow, persists the outcome and shapes the response. It is the only
place that knows about both HTTP concerns and the graph.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import (
    EVENT_INVALID_REQUEST,
    EVENT_TRIP_DELETED,
    EVENT_TRIP_PLANNED,
    REVIEW_AWAITING,
    TRIP_AWAITING_REVIEW,
)
from app.core.exceptions import TripNotFound
from app.db.models import Trip
from app.db.repositories import ReviewRepository, TripRepository
from app.graph.state import TravelState
from app.graph.travel_graph import TravelWorkflow, get_workflow
from app.guardrails import input_guard
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.tracing import set_trip_id
from app.schemas.review import ReviewRecord
from app.schemas.travel import (
    GuardrailBlockedResponse,
    TripDetailResponse,
    TripListResponse,
    TripPlanRequest,
    TripPlanResponse,
    TripSummary,
)
from app.security import audit
from app.services.conversation_service import ConversationService

logger = get_logger("journeymesh.services.travel")


class TravelService:
    def __init__(self, session: Session, workflow: TravelWorkflow | None = None) -> None:
        self.session = session
        self.trips = TripRepository(session)
        self.reviews = ReviewRepository(session)
        self.conversations = ConversationService(session)
        self.workflow = workflow or get_workflow()

    # ---- planning --------------------------------------------------------
    async def plan(
        self, request: TripPlanRequest, *, request_id: str | None = None
    ) -> TripPlanResponse | GuardrailBlockedResponse:
        decision = input_guard.check_request(request)
        if not decision.allowed:
            audit.record(
                EVENT_INVALID_REQUEST
                if decision.reason_code != "prompt_injection_blocked"
                else "PROMPT_INJECTION_BLOCKED",
                detail={"reason_code": decision.reason_code},
                session=self.session,
            )
            metrics.increment("plan.blocked", reason=decision.reason_code or "unknown")
            return GuardrailBlockedResponse(
                reason_code=decision.reason_code or "guardrail_blocked",
                message=decision.message or "This request was blocked.",
                guidance=decision.guidance,
            )

        trip_id = str(uuid.uuid4())
        set_trip_id(trip_id)

        state = await self.workflow.plan(
            trip_id=trip_id,
            request=request,
            sanitized_query=decision.sanitized_query,
            request_id=request_id,
        )
        state.setdefault("guardrail_results", []).insert(0, decision.to_dict())

        trip = self._persist_new_trip(request, state, decision)
        self.reviews.add(
            trip.id,
            revision_number=1,
            review_status=state.get("human_review_status", REVIEW_AWAITING),
            selected_agents=list(state.get("selected_agents") or []),
            change_scope=[],
        )
        self.conversations.persist_state_messages(state)
        audit.record(
            EVENT_TRIP_PLANNED,
            detail={"selected_agents": state.get("selected_agents")},
            trip_id=trip.id,
            session=self.session,
        )
        metrics.increment("plan.completed")
        return self._to_response(trip, state)

    # ---- reads -----------------------------------------------------------
    def get(self, trip_id: str) -> TripDetailResponse:
        trip = self.trips.get(trip_id)
        if trip is None:
            raise TripNotFound(f"No journey with id {trip_id}")

        state = self.workflow.load_state(trip_id) or self._state_from_db(trip)
        response = self._to_response(trip, state)
        detail = TripDetailResponse(**response.model_dump())
        detail.reviews = [
            ReviewRecord(
                revision_number=review.revision_number,
                review_status=review.review_status,  # type: ignore[arg-type]
                requested_changes=review.requested_changes,
                selected_agents=list(review.selected_agents or []),
                change_scope=list(review.change_scope or []),
                reviewed_at=review.reviewed_at,
            )
            for review in trip.reviews
        ]
        return detail

    def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        session_id: str | None = None,
        status: str | None = None,
    ) -> TripListResponse:
        trips = self.trips.list(limit=limit, offset=offset, session_id=session_id, status=status)
        total = self.trips.count(session_id=session_id, status=status)
        return TripListResponse(
            items=[self._to_summary(trip) for trip in trips],
            total=total,
            limit=limit,
            offset=offset,
        )

    def delete(self, trip_id: str) -> None:
        trip = self.trips.get(trip_id)
        if trip is None:
            raise TripNotFound(f"No journey with id {trip_id}")
        self.trips.delete(trip)
        audit.record(EVENT_TRIP_DELETED, trip_id=trip_id, session=self.session)

    # ---- persistence -----------------------------------------------------
    def _persist_new_trip(
        self, request: TripPlanRequest, state: TravelState, decision: Any
    ) -> Trip:
        constraints = state.get("trip_constraints") or {}
        trip = self.trips.create(
            id=state["trip_id"],
            session_id=request.session_id,
            user_query=decision.sanitized_query or request.query,
            origin=request.origin,
            destination=request.destination,
            departure_date=request.departure_date,
            return_date=request.return_date,
            travelers=request.travelers,
            budget=request.budget,
            currency=request.currency,
            travel_style=request.travel_style,
            hotel_preference=request.hotel_preference,
            interests=list(request.interests),
            special_requirements=request.special_requirements,
            additional_instructions=request.additional_instructions,
            preferred_language=request.response_language,
            status=state.get("trip_status", TRIP_AWAITING_REVIEW),
            review_status=state.get("human_review_status", REVIEW_AWAITING),
            revision_count=int(state.get("revision_count", 1)),
            constraints=constraints,
            selected_agents=list(state.get("selected_agents") or []),
        )
        self.save_results(trip.id, state)
        return trip

    def save_results(self, trip_id: str, state: TravelState) -> None:
        self.trips.upsert_result(
            trip_id,
            flight_results=state.get("flight_results") or {},
            hotel_results=state.get("hotel_results") or {},
            weather_results=state.get("weather_info") or {},
            budget_analysis=state.get("budget_analysis") or {},
            itinerary=state.get("itinerary_plan") or {},
            final_summary=state.get("final_response") or {},
            provider_metadata=state.get("provider_status") or [],
            evaluation_summary=state.get("evaluation_results") or {},
            guardrail_summary=state.get("guardrail_results") or [],
        )

    def _state_from_db(self, trip: Trip) -> TravelState:
        """Rebuild a state view from persisted rows when no checkpoint exists."""
        result = trip.result
        state: TravelState = {  # type: ignore[assignment]
            "trip_id": trip.id,
            "session_id": trip.session_id,
            "user_query": trip.user_query,
            "trip_constraints": dict(trip.constraints or {}),
            "response_language": trip.preferred_language,
            "selected_agents": list(trip.selected_agents or []),
            "human_review_status": trip.review_status,
            "trip_status": trip.status,
            "revision_count": trip.revision_count,
            "flight_results": dict((result.flight_results if result else {}) or {}),
            "hotel_results": dict((result.hotel_results if result else {}) or {}),
            "weather_info": dict((result.weather_results if result else {}) or {}),
            "budget_analysis": dict((result.budget_analysis if result else {}) or {}),
            "itinerary_plan": dict((result.itinerary if result else {}) or {}),
            "final_response": dict((result.final_summary if result else {}) or {}),
            "provider_status": list((result.provider_metadata if result else []) or []),
            "evaluation_results": dict((result.evaluation_summary if result else {}) or {}),
            "guardrail_results": list((result.guardrail_summary if result else []) or []),
            "messages": [],
            "created_at": trip.created_at.isoformat() if trip.created_at else "",
            "updated_at": trip.updated_at.isoformat() if trip.updated_at else "",
        }
        return state

    # ---- shaping ---------------------------------------------------------
    def _to_response(self, trip: Trip, state: TravelState) -> TripPlanResponse:
        return TripPlanResponse(
            trip_id=trip.id,
            session_id=trip.session_id,
            status=state.get("trip_status", trip.status),
            review_status=state.get("human_review_status", trip.review_status),  # type: ignore[arg-type]
            revision=int(state.get("revision_count", trip.revision_count)),
            selected_agents=list(state.get("selected_agents") or []),
            execution_reason=state.get("execution_reason"),
            constraints=state.get("trip_constraints") or {},  # type: ignore[arg-type]
            flights=state.get("flight_results") or {},  # type: ignore[arg-type]
            hotels=state.get("hotel_results") or {},  # type: ignore[arg-type]
            weather=state.get("weather_info") or {},  # type: ignore[arg-type]
            budget=state.get("budget_analysis") or {},  # type: ignore[arg-type]
            itinerary=state.get("itinerary_plan") or {},  # type: ignore[arg-type]
            provider_status=state.get("provider_status") or [],  # type: ignore[arg-type]
            evaluation=state.get("evaluation_results") or None,  # type: ignore[arg-type]
            guardrails=list(state.get("guardrail_results") or []),
            final_journey=state.get("final_response") or None,  # type: ignore[arg-type]
            messages=[
                message.get("content", "")
                for message in (state.get("messages") or [])
                if message.get("role") in {"supervisor", "agent", "system"}
            ],
            created_at=trip.created_at,
            updated_at=trip.updated_at,
        )

    def _to_summary(self, trip: Trip) -> TripSummary:
        evaluation = (trip.result.evaluation_summary if trip.result else {}) or {}
        return TripSummary(
            trip_id=trip.id,
            session_id=trip.session_id,
            origin=trip.origin,
            destination=trip.destination,
            departure_date=trip.departure_date,
            return_date=trip.return_date,
            travelers=trip.travelers,
            budget=trip.budget,
            currency=trip.currency,
            travel_style=trip.travel_style,
            status=trip.status,
            review_status=trip.review_status,  # type: ignore[arg-type]
            revision_count=trip.revision_count,
            preferred_language=trip.preferred_language,  # type: ignore[arg-type]
            evaluation_score=evaluation.get("overall_score"),
            created_at=trip.created_at,
            updated_at=trip.updated_at,
        )
