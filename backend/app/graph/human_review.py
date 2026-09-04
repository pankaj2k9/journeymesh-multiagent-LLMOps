"""The human review pause, expressed with LangGraph's native primitives.

    specialists -> output_guard -> evaluation -> human_review
                                                     |
                                                 interrupt()      <-- pauses
                                                     |
                                          Command(resume={...})   <-- continues
                                                     |
                                    approve ---> final_response -> END
                                    changes ---> supervisor_revision -> ...

`interrupt()` raises a control-flow signal that LangGraph catches. The
checkpointer writes the state as it stood at that instant, including which
node was mid-execution, and `ainvoke` returns with an `__interrupt__` payload
instead of a finished state. Nothing is lost and nothing is re-run: when
`Command(resume=value)` arrives, the *same* node call resumes and `interrupt()`
returns `value` as though it had simply been a slow function.

That is the difference from ending the graph and re-entering it. Re-entry has
to reconstruct where it was from stored fields; a resume genuinely continues.
It also means the review decision is applied inside the graph, where the
routing that follows can see it.

This module owns the shapes on both sides of that pause so that the graph, the
service layer and the tests agree on one contract.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.core.constants import (
    REVIEW_APPROVED,
    REVIEW_AWAITING,
    REVIEW_CHANGES_REQUESTED,
    REVIEW_LIMIT_REACHED,
)

# ---- the resume contract ---------------------------------------------------
ACTION_APPROVE = "approve"
ACTION_REQUEST_CHANGES = "request_changes"
ACTION_REJECT = "reject"

ReviewAction = Literal["approve", "request_changes", "reject"]

VALID_ACTIONS = (ACTION_APPROVE, ACTION_REQUEST_CHANGES, ACTION_REJECT)


class ReviewDecision(TypedDict, total=False):
    """What `Command(resume=...)` carries back into the paused node."""

    action: ReviewAction
    feedback: str
    response_language: str
    note: str


class ReviewRequest(TypedDict, total=False):
    """What `interrupt()` hands to whoever is waiting.

    Everything a reviewer needs to decide, and nothing they do not: no raw
    provider payloads, no credentials, no internal identifiers beyond the trip.
    """

    kind: Literal["human_review"]
    trip_id: str
    revision: int
    review_status: str
    limit_reached: bool
    itinerary: dict[str, Any]
    budget: dict[str, Any]
    evaluation: dict[str, Any]
    selected_agents: list[str]
    agents_run: list[str]
    provider_status: list[dict[str, Any]]
    actions: list[str]
    prompt: str


def build_request(state: dict[str, Any], *, limit_reached: bool) -> ReviewRequest:
    """The payload handed to `interrupt()`."""
    actions = [ACTION_APPROVE] if limit_reached else [ACTION_APPROVE, ACTION_REQUEST_CHANGES]
    prompt = (
        "The revision limit has been reached. Approve the current journey or "
        "start a new one."
        if limit_reached
        else "Review the draft journey. Approve it, or describe the changes you want."
    )
    return {
        "kind": "human_review",
        "trip_id": str(state.get("trip_id") or ""),
        "revision": int(state.get("revision_count", 1)),
        "review_status": REVIEW_LIMIT_REACHED if limit_reached else REVIEW_AWAITING,
        "limit_reached": limit_reached,
        "itinerary": state.get("itinerary_plan") or {},
        "budget": state.get("budget_analysis") or {},
        "evaluation": state.get("evaluation_results") or {},
        "selected_agents": list(state.get("selected_agents") or []),
        "agents_run": list(state.get("agents_run") or []),
        "provider_status": list(state.get("provider_status") or []),
        "actions": actions,
        "prompt": prompt,
    }


def normalise_decision(value: Any) -> ReviewDecision:
    """Coerce whatever arrived in `Command(resume=...)` into a known shape.

    A resume value comes from outside the graph, so it is validated here rather
    than trusted. An unrecognised action is treated as "still waiting", which
    leaves the journey reviewable instead of silently finalising it.
    """
    if not isinstance(value, dict):
        return {"action": ACTION_APPROVE} if value is True else {}

    raw_action = str(value.get("action") or "").strip().lower()
    if raw_action not in VALID_ACTIONS:
        # Tolerate the older boolean-shaped payload.
        if value.get("approved") is True:
            raw_action = ACTION_APPROVE
        elif value.get("feedback") or value.get("requested_changes"):
            raw_action = ACTION_REQUEST_CHANGES
        else:
            return {}

    decision: ReviewDecision = {"action": raw_action}  # type: ignore[typeddict-item]
    feedback = value.get("feedback") or value.get("requested_changes") or ""
    if feedback:
        decision["feedback"] = str(feedback).strip()
    if value.get("response_language"):
        decision["response_language"] = str(value["response_language"])
    if value.get("note"):
        decision["note"] = str(value["note"])
    return decision


def status_for(action: str | None) -> str:
    """The persisted review status an action produces."""
    if action == ACTION_APPROVE:
        return REVIEW_APPROVED
    if action == ACTION_REQUEST_CHANGES:
        return REVIEW_CHANGES_REQUESTED
    if action == ACTION_REJECT:
        return REVIEW_AWAITING
    return REVIEW_AWAITING
