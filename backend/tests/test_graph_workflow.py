"""The LangGraph workflow: pause for review, resume, and selective re-execution."""

from __future__ import annotations

import pytest

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_a_plan_pauses_at_human_review(workflow, family_request):
    state = await workflow.plan(trip_id="trip-hitl", request=family_request)

    assert state["human_review_status"] == "awaiting_review"
    assert state["trip_status"] == "awaiting_review"
    assert state["final_response"] == {}
    assert state["selected_agents"]
    assert state["evaluation_results"]["overall_score"] > 0
    assert not state["errors"]


@pytest.mark.asyncio
async def test_the_paused_run_is_checkpointed_and_can_be_reloaded(workflow, family_request):
    await workflow.plan(trip_id="trip-checkpoint", request=family_request)

    restored = workflow.load_state("trip-checkpoint")
    assert restored is not None
    assert restored["trip_id"] == "trip-checkpoint"
    assert restored["human_review_status"] == "awaiting_review"
    assert restored["itinerary_plan"]["days"]


@pytest.mark.asyncio
async def test_approval_resumes_the_workflow_and_produces_the_final_journey(
    workflow, family_request
):
    state = await workflow.plan(trip_id="trip-approve", request=family_request)
    approved = await workflow.approve(state)

    assert approved["human_review_status"] == "approved"
    assert approved["trip_status"] == "approved"
    assert approved["final_response"]["overview"]["title"]
    assert approved["final_response"]["itinerary"]["days"]


@pytest.mark.asyncio
async def test_a_cheaper_hotel_request_reruns_only_the_affected_agents(workflow, family_request):
    state = await workflow.plan(trip_id="trip-revise", request=family_request)

    flights_before = state["flight_results"]
    weather_before = state["weather_info"]
    hotel_before = state["hotel_results"]

    revised = await workflow.revise(
        state,
        requested_changes="The hotel is too expensive. Find cheaper hotels under $90 per night.",
    )

    assert revised["selected_agents"] == ["hotel_agent", "budget_agent", "itinerary_agent"]
    assert "flight_agent" not in revised["agents_run"]
    assert "weather_agent" not in revised["agents_run"]

    # Untouched slices are preserved verbatim.
    assert revised["flight_results"] == flights_before
    assert revised["weather_info"] == weather_before

    # The hotel slice was replaced and now respects the new ceiling.
    assert revised["hotel_results"] != hotel_before
    assert revised["hotel_results"]["options"][0]["price_per_night"] <= 90

    # Budget and itinerary were refreshed on top of the new hotel.
    assert revised["budget_analysis"]["breakdown"]["hotels"] > 0
    assert revised["itinerary_plan"]["days"]
    assert revised["revision_count"] == 2


@pytest.mark.asyncio
async def test_changing_the_flight_preserves_the_hotel(workflow, family_request):
    state = await workflow.plan(trip_id="trip-flight-change", request=family_request)
    hotel_before = state["hotel_results"]
    weather_before = state["weather_info"]

    revised = await workflow.revise(
        state, requested_changes="Change my departure flight to a morning departure."
    )

    assert "flight_agent" in revised["selected_agents"]
    assert "hotel_agent" not in revised["selected_agents"]
    assert revised["hotel_results"] == hotel_before
    assert revised["weather_info"] == weather_before


@pytest.mark.asyncio
async def test_the_revision_counter_increases_with_each_round(workflow, family_request):
    state = await workflow.plan(trip_id="trip-count", request=family_request)
    assert state["revision_count"] == 1

    state = await workflow.revise(state, requested_changes="Find a cheaper hotel.")
    assert state["revision_count"] == 2

    state = await workflow.revise(state, requested_changes="Add more nature activities.")
    assert state["revision_count"] == 3


@pytest.mark.asyncio
async def test_the_revision_limit_stops_the_loop(workflow, family_request):
    limit = get_settings().max_revision_count
    state = await workflow.plan(trip_id="trip-limit", request=family_request)

    for index in range(limit + 1):
        state = await workflow.revise(
            state, requested_changes=f"Adjust the daily activities, round {index}."
        )

    assert state["revision_count"] > limit
    assert state["human_review_status"] == "revision_limit_reached"


@pytest.mark.asyncio
async def test_a_weather_only_question_runs_one_agent(workflow):
    from app.schemas.travel import TripPlanRequest

    request = TripPlanRequest(
        query="What will the weather be like in Dubai next week?",
        destination="Dubai",
        response_language="en",
    )
    state = await workflow.plan(trip_id="trip-weather", request=request)

    assert state["selected_agents"] == ["weather_agent"]
    assert state["weather_info"]["forecast"]
    assert state["flight_results"] == {}
    assert state["hotel_results"] == {}


@pytest.mark.asyncio
async def test_execution_notes_never_contain_model_reasoning(workflow, family_request):
    state = await workflow.plan(trip_id="trip-notes", request=family_request)
    blob = " ".join(message["content"] for message in state["messages"]).lower()
    for marker in ("chain of thought", "my reasoning", "<thinking>", "system prompt"):
        assert marker not in blob
