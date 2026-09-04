"""Human-in-the-loop through LangGraph's native interrupt and resume.

These tests drive the real graph with a real checkpointer. Nothing here fakes
the pause by editing state: the workflow is genuinely suspended inside
``interrupt()``, the checkpoint is read back, and it is continued with
``Command(resume=...)``. That is the behaviour worth protecting, because it is
the difference between a workflow that survives a process restart and one that
only looks like it does.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.core.constants import REVIEW_APPROVED, REVIEW_AWAITING
from app.graph.human_review import (
    ACTION_APPROVE,
    ACTION_REQUEST_CHANGES,
    normalise_decision,
)
from app.graph.travel_graph import TravelWorkflow
from app.schemas.travel import TripPlanRequest

QUERY = "Plan a 4-day trip from Dhaka to Singapore for 2 people with a 3000 USD budget."


@pytest.fixture()
def workflow() -> TravelWorkflow:
    # MemorySaver rather than PostgreSQL: the interrupt semantics are the same
    # and the suite stays hermetic.
    return TravelWorkflow(checkpointer=MemorySaver())


def _request() -> TripPlanRequest:
    return TripPlanRequest(query=QUERY, response_language="en")


# ---------------------------------------------------------------------------
# The pause
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_plan_suspends_inside_the_interrupt(workflow):
    state = await workflow.plan(trip_id="t-int-1", request=_request())

    # LangGraph reports the pause rather than returning a finished state.
    assert "__interrupt__" in state
    payload = state["__interrupt__"][0].value
    assert payload["kind"] == "human_review"
    assert payload["trip_id"] == "t-int-1"
    assert set(payload["actions"]) == {ACTION_APPROVE, ACTION_REQUEST_CHANGES}
    # Enough to decide with, and nothing a reviewer should not see.
    assert payload["itinerary"]
    assert "api_key" not in repr(payload).lower()


@pytest.mark.asyncio
async def test_the_awaiting_status_is_committed_before_the_pause(workflow):
    """A node's changes persist from its return value, and interrupt raises.

    So the status is set by the node *before* the one that interrupts. If that
    ever regresses, the API reports a journey as pending while it is actually
    waiting for a person.
    """
    state = await workflow.plan(trip_id="t-int-2", request=_request())
    assert state["human_review_status"] == REVIEW_AWAITING

    snapshot = workflow.graph.get_state(workflow.config("t-int-2"))
    assert snapshot.values["human_review_status"] == REVIEW_AWAITING


@pytest.mark.asyncio
async def test_the_checkpoint_records_the_suspended_node(workflow):
    await workflow.plan(trip_id="t-int-3", request=_request())

    snapshot = workflow.graph.get_state(workflow.config("t-int-3"))
    assert snapshot.next == ("human_review",)
    assert workflow._has_pending_interrupt("t-int-3") is True


@pytest.mark.asyncio
async def test_no_pending_interrupt_on_an_unknown_thread(workflow):
    assert workflow._has_pending_interrupt("never-planned") is False


# ---------------------------------------------------------------------------
# Resume: approve
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approval_resumes_the_graph_and_finalises(workflow):
    await workflow.plan(trip_id="t-int-4", request=_request())
    paused = workflow.graph.get_state(workflow.config("t-int-4")).values

    final = await workflow.approve(dict(paused))

    assert "__interrupt__" not in final
    assert final["human_review_status"] == REVIEW_APPROVED
    assert final["final_response"]
    # The decision that resumed the graph is recorded, not inferred.
    assert final["review_decision"]["action"] == ACTION_APPROVE


@pytest.mark.asyncio
async def test_approval_does_not_re_run_the_specialists(workflow):
    """Approving must not re-plan; that is the whole point of resuming."""
    await workflow.plan(trip_id="t-int-5", request=_request())
    paused = workflow.graph.get_state(workflow.config("t-int-5")).values
    itinerary_before = paused["itinerary_plan"]

    final = await workflow.approve(dict(paused))

    assert final["itinerary_plan"] == itinerary_before


# ---------------------------------------------------------------------------
# Resume: request changes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requesting_changes_resumes_revises_and_pauses_again(workflow):
    await workflow.plan(trip_id="t-int-6", request=_request())
    paused = workflow.graph.get_state(workflow.config("t-int-6")).values

    after = await workflow.revise(dict(paused), requested_changes="Find cheaper hotels")

    # It returned to the review pause rather than finishing.
    assert "__interrupt__" in after
    values = workflow.graph.get_state(workflow.config("t-int-6")).values
    assert values["revision_count"] == 2
    assert values["human_review_status"] == REVIEW_AWAITING
    # Only the agents the change affects ran again.
    assert "hotel_agent" in values["agents_run"]
    assert "flight_agent" not in values["agents_run"]


@pytest.mark.asyncio
async def test_a_revision_can_be_approved_afterwards(workflow):
    await workflow.plan(trip_id="t-int-7", request=_request())
    paused = workflow.graph.get_state(workflow.config("t-int-7")).values
    await workflow.revise(dict(paused), requested_changes="Add a museum on day two")

    revised = workflow.graph.get_state(workflow.config("t-int-7")).values
    final = await workflow.approve(dict(revised))

    assert final["human_review_status"] == REVIEW_APPROVED
    assert final["final_response"]


# ---------------------------------------------------------------------------
# The resume contract
# ---------------------------------------------------------------------------
def test_an_unrecognised_resume_value_leaves_the_journey_reviewable():
    """A decision nobody made must not finalise a journey."""
    assert normalise_decision({"action": "sabotage"}) == {}
    assert normalise_decision(None) == {}
    assert normalise_decision("approve") == {}


def test_the_older_boolean_shaped_payload_is_still_understood():
    assert normalise_decision({"approved": True})["action"] == ACTION_APPROVE
    decision = normalise_decision({"feedback": "cheaper please"})
    assert decision["action"] == ACTION_REQUEST_CHANGES
    assert decision["feedback"] == "cheaper please"


def test_a_change_request_carries_its_feedback():
    decision = normalise_decision(
        {"action": "request_changes", "feedback": "  more museums  "}
    )
    assert decision["action"] == ACTION_REQUEST_CHANGES
    assert decision["feedback"] == "more museums"


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_second_workflow_object_can_resume_the_same_thread():
    """The pause lives in the checkpoint, not in the Python object.

    This is what makes the pattern work across a FastAPI worker restart: a new
    process builds a new workflow, reads the same checkpointer, and continues
    the run somebody else started.
    """
    saver = MemorySaver()
    first = TravelWorkflow(checkpointer=saver)
    await first.plan(trip_id="t-int-8", request=_request())

    second = TravelWorkflow(checkpointer=saver)
    assert second._has_pending_interrupt("t-int-8") is True

    paused = second.graph.get_state(second.config("t-int-8")).values
    final = await second.approve(dict(paused))

    assert final["human_review_status"] == REVIEW_APPROVED
    assert final["final_response"]


@pytest.mark.asyncio
async def test_a_lost_checkpoint_still_completes_the_decision():
    """A journey reviewed after a restart with no checkpoint must not be stuck.

    MemorySaver loses everything when a process ends, and a restored database
    may have no checkpoint row. The native path is Command(resume=...); this is
    the documented fallback, and it has to produce the same outcome.
    """
    first = TravelWorkflow(checkpointer=MemorySaver())
    await first.plan(trip_id="t-int-9", request=_request())
    paused = first.graph.get_state(first.config("t-int-9")).values

    # A brand new checkpointer: the pause is gone.
    second = TravelWorkflow(checkpointer=MemorySaver())
    assert second._has_pending_interrupt("t-int-9") is False

    final = await second.approve(dict(paused))
    assert final["human_review_status"] == REVIEW_APPROVED
    assert final["final_response"]
