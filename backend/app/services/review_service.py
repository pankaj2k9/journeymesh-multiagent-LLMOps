"""Human-in-the-loop review service.

Approve resumes the workflow and produces the final journey. Request-changes
hands the traveller's words to the Supervisor, which re-runs only the affected
agents. A revision limit stops the loop from running forever.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    EVENT_HUMAN_REVIEW_APPROVED,
    EVENT_HUMAN_REVIEW_CHANGES_REQUESTED,
    EVENT_REVISION_LIMIT_REACHED,
    REVIEW_APPROVED,
    REVIEW_AWAITING,
    REVIEW_CHANGES_REQUESTED,
    REVIEW_LIMIT_REACHED,
    TRIP_APPROVED,
)
from app.core.exceptions import (
    GuardrailRejection,
    InvalidReviewState,
    RevisionLimitReached,
    TripNotFound,
)
from app.db.models import Trip
from app.db.repositories import ReviewRepository, TripRepository
from app.graph.state import TravelState
from app.graph.travel_graph import TravelWorkflow, get_workflow
from app.guardrails import input_guard
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.tracing import set_trip_id, span
from app.schemas.review import ApproveResponse, ChangeResponse
from app.security import audit
from app.services.conversation_service import ConversationService
from app.services.travel_service import TravelService

logger = get_logger("journeymesh.services.review")

_REVIEWABLE = {REVIEW_AWAITING, REVIEW_CHANGES_REQUESTED, REVIEW_LIMIT_REACHED}


class ReviewService:
    def __init__(self, session: Session, workflow: TravelWorkflow | None = None) -> None:
        self.session = session
        self.trips = TripRepository(session)
        self.reviews = ReviewRepository(session)
        self.conversations = ConversationService(session)
        self.workflow = workflow or get_workflow()
        self.travel = TravelService(session, workflow=self.workflow)

    # ---- approve ---------------------------------------------------------
    async def approve(
        self, trip_id: str, *, response_language: str | None = None, note: str | None = None
    ) -> ApproveResponse:
        trip = self._load_trip(trip_id)
        if trip.review_status == REVIEW_APPROVED:
            raise InvalidReviewState("This journey has already been approved.")
        if trip.review_status not in _REVIEWABLE:
            raise InvalidReviewState("This journey is not awaiting a review decision.")

        state = self._load_state(trip)
        if response_language:
            constraints = dict(state.get("trip_constraints") or {})
            constraints["response_language"] = response_language
            state["trip_constraints"] = constraints
            state["response_language"] = response_language

        state = await self.workflow.approve(state)

        self.trips.update(
            trip,
            status=TRIP_APPROVED,
            review_status=REVIEW_APPROVED,
            preferred_language=response_language or trip.preferred_language,
        )
        self.travel.save_results(trip.id, state)
        self.reviews.add(
            trip.id,
            revision_number=int(state.get("revision_count", trip.revision_count)),
            review_status=REVIEW_APPROVED,
            reviewer_note=note,
            selected_agents=list(state.get("selected_agents") or []),
            change_scope=[],
        )
        self.conversations.persist_state_messages(state)
        audit.record(
            EVENT_HUMAN_REVIEW_APPROVED, trip_id=trip.id, session=self.session
        )
        metrics.increment("review.approved")

        return ApproveResponse(
            trip_id=trip.id,
            status=REVIEW_APPROVED,
            revision=int(state.get("revision_count", trip.revision_count)),
            final_summary=state.get("final_response") or None,
        )

    # ---- request changes -------------------------------------------------
    async def request_changes(
        self, trip_id: str, *, requested_changes: str, response_language: str | None = None
    ) -> ChangeResponse:
        settings = get_settings()
        trip = self._load_trip(trip_id)

        if trip.review_status == REVIEW_APPROVED:
            raise InvalidReviewState(
                "This journey has already been approved. Start a new journey to change it."
            )
        if trip.revision_count >= settings.max_revision_count:
            audit.record(
                EVENT_REVISION_LIMIT_REACHED, trip_id=trip.id, session=self.session
            )
            self.trips.update(trip, review_status=REVIEW_LIMIT_REACHED)
            raise RevisionLimitReached(
                f"This journey has already been revised {trip.revision_count} time(s)."
            )

        with span("Input Guard", kind="guardrail", stage="change_request"):
            decision = input_guard.check_change_request(requested_changes)

        if not decision.allowed:
            audit.record(
                "PROMPT_INJECTION_BLOCKED"
                if decision.reason_code == "prompt_injection_blocked"
                else "INVALID_REQUEST",
                detail={"reason_code": decision.reason_code},
                trip_id=trip.id,
                session=self.session,
            )
            raise GuardrailRejection(
                decision.message or "That change request was blocked.",
                code=decision.reason_code or "guardrail_blocked",
            )

        set_trip_id(trip.id)
        state = self._load_state(trip)
        if response_language:
            constraints = dict(state.get("trip_constraints") or {})
            constraints["response_language"] = response_language
            state["trip_constraints"] = constraints
            state["response_language"] = response_language

        state = await self.workflow.revise(
            state, requested_changes=decision.sanitized_query
        )

        revision = int(state.get("revision_count", trip.revision_count + 1))
        review_status = state.get("human_review_status", REVIEW_AWAITING)
        self.trips.update(
            trip,
            status=state.get("trip_status", trip.status),
            review_status=review_status,
            revision_count=revision,
            selected_agents=list(state.get("selected_agents") or []),
            constraints=state.get("trip_constraints") or trip.constraints,
            preferred_language=response_language or trip.preferred_language,
        )
        self.travel.save_results(trip.id, state)
        self.reviews.add(
            trip.id,
            revision_number=revision,
            review_status=REVIEW_CHANGES_REQUESTED,
            requested_changes=decision.sanitized_query,
            selected_agents=list(state.get("selected_agents") or []),
            change_scope=list(state.get("change_scope") or []),
            reviewed_at=datetime.now(timezone.utc),
        )
        self.conversations.persist_state_messages(state)
        audit.record(
            EVENT_HUMAN_REVIEW_CHANGES_REQUESTED,
            detail={
                "selected_agents": state.get("selected_agents"),
                "change_scope": state.get("change_scope"),
            },
            trip_id=trip.id,
            session=self.session,
        )
        metrics.increment("review.changes_requested")

        return ChangeResponse(
            trip_id=trip.id,
            revision=revision,
            selected_agents=list(state.get("selected_agents") or []),
            change_scope=list(state.get("change_scope") or []),
            status=review_status,
        )

    # ---- regenerate ------------------------------------------------------
    async def regenerate(self, trip_id: str) -> ChangeResponse:
        """Re-run the full plan for a journey, respecting the revision limit."""
        return await self.request_changes(
            trip_id,
            requested_changes=(
                "Regenerate the whole journey: flights, hotels, weather, budget and itinerary."
            ),
        )

    # ---- helpers ---------------------------------------------------------
    def _load_trip(self, trip_id: str) -> Trip:
        trip = self.trips.get(trip_id)
        if trip is None:
            raise TripNotFound(f"No journey with id {trip_id}")
        set_trip_id(trip.id)
        return trip

    def _load_state(self, trip: Trip) -> TravelState:
        state = self.workflow.load_state(trip.id)
        if state:
            return state
        logger.info(
            "no checkpoint found, rebuilding state from storage", extra={"trip_id": trip.id}
        )
        return self.travel._state_from_db(trip)
