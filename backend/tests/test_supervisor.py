"""Dynamic agent selection and revision routing."""

from __future__ import annotations

import pytest

from app.agents.supervisor import SupervisorAgent, expand_dependents, preservation_requests
from app.graph.state import new_state

SUPERVISOR = SupervisorAgent()


def state_for(query: str, **constraints):
    base = {"response_language": "en", "travelers": 1, "currency": "USD"}
    base.update(constraints)
    return new_state(trip_id="t", user_query=query, trip_constraints=base)


@pytest.mark.asyncio
async def test_a_weather_question_runs_only_the_weather_agent():
    state = state_for("What will the weather be like in Dubai next week?", destination="Dubai")
    await SUPERVISOR.plan(state)
    assert state["selected_agents"] == ["weather_agent"]


@pytest.mark.asyncio
async def test_a_full_trip_runs_every_specialist():
    state = state_for(
        "Plan a 5-day family trip to Dubai under $3,000",
        origin="Dhaka",
        destination="Dubai",
        departure_date="2027-02-01",
        return_date="2027-02-05",
        budget=3000,
        nights=4,
        trip_days=5,
    )
    await SUPERVISOR.plan(state)
    assert state["selected_agents"] == [
        "flight_agent",
        "hotel_agent",
        "weather_agent",
        "budget_agent",
        "itinerary_agent",
    ]
    assert state["execution_reason"]


@pytest.mark.asyncio
async def test_a_hotel_only_question_does_not_run_flights():
    state = state_for("Find me a quiet hotel in Kyoto", destination="Kyoto")
    await SUPERVISOR.plan(state)
    assert "hotel_agent" in state["selected_agents"]
    assert "flight_agent" not in state["selected_agents"]


def test_dependents_are_expanded():
    assert expand_dependents({"hotel_agent"}) == {
        "hotel_agent",
        "budget_agent",
        "itinerary_agent",
    }
    assert expand_dependents({"weather_agent"}) == {"weather_agent", "itinerary_agent"}


def test_preservation_phrases_are_understood():
    assert preservation_requests("keep my flights") == {"flight_agent"}
    assert preservation_requests("don't change the hotel") == {"hotel_agent"}
    assert preservation_requests("find something cheaper") == set()


def test_a_cheaper_hotel_request_reruns_only_three_agents():
    state = state_for("Plan a trip", destination="Dubai")
    state["flight_results"] = {"options": [{"airline": "A"}]}
    state["hotel_results"] = {"options": [{"name": "B"}]}
    state["weather_info"] = {"forecast": [{"date": "2027-02-01"}]}

    analysis = SUPERVISOR.analyse_change(state, "Find a cheaper hotel under $120 per night.")
    assert analysis["selected_agents"] == ["hotel_agent", "budget_agent", "itinerary_agent"]
    assert "flight_agent" in analysis["preserved_agents"]
    assert "weather_agent" in analysis["preserved_agents"]
    assert analysis["constraint_updates"]["max_hotel_price_per_night"] == 120


def test_keeping_flights_wins_over_the_word_flights():
    state = state_for("Plan a trip", destination="Dubai")
    state["flight_results"] = {"options": [{"airline": "A"}]}
    state["hotel_results"] = {"options": [{"name": "B"}]}
    state["weather_info"] = {"forecast": []}

    analysis = SUPERVISOR.analyse_change(
        state, "Find a cheaper hotel under $80 per night, keep my flights."
    )
    assert "flight_agent" not in analysis["selected_agents"]
    assert "flight_agent" in analysis["preserved_agents"]


def test_changing_the_departure_flight_preserves_the_hotel():
    state = state_for("Plan a trip", destination="Dubai")
    state["flight_results"] = {"options": [{"airline": "A"}]}
    state["hotel_results"] = {"options": [{"name": "B"}]}
    state["weather_info"] = {"forecast": [{"date": "2027-02-01"}]}

    analysis = SUPERVISOR.analyse_change(state, "Change my departure flight to the morning.")
    assert analysis["selected_agents"] == ["flight_agent", "budget_agent", "itinerary_agent"]
    assert "hotel_agent" in analysis["preserved_agents"]
    assert "weather_agent" in analysis["preserved_agents"]


def test_bad_weather_adjusts_activities_without_refetching_the_forecast():
    state = state_for("Plan a trip", destination="Dubai")
    state["weather_info"] = {"forecast": [{"date": "2027-02-01"}]}
    state["flight_results"] = {"options": [{"airline": "A"}]}

    analysis = SUPERVISOR.analyse_change(
        state, "The weather looks bad. Change the activities accordingly."
    )
    assert "itinerary_agent" in analysis["selected_agents"]
    assert "weather_agent" not in analysis["selected_agents"]


def test_a_whole_trip_budget_cut_touches_the_large_cost_lines():
    state = state_for("Plan a trip", destination="Dubai", budget=3000)
    state["flight_results"] = {"options": [{"airline": "A"}]}
    state["hotel_results"] = {"options": [{"name": "B"}]}

    analysis = SUPERVISOR.analyse_change(state, "Reduce the entire trip below $2,000.")
    assert {"budget_agent", "hotel_agent", "flight_agent"} <= set(analysis["selected_agents"])
    assert analysis["constraint_updates"]["budget"] == 2000


@pytest.mark.asyncio
async def test_the_trip_length_is_read_from_free_text_when_no_dates_are_given():
    from app.agents.supervisor import duration_from_text

    assert duration_from_text("a 5-day family trip") == (5, 4)
    assert duration_from_text("3 nights in Kyoto") == (4, 3)
    assert duration_from_text("four days in Rome") == (4, 3)
    assert duration_from_text("a trip to Rome") == (None, None)

    state = state_for("Plan a 4-day relaxing trip to Kyoto for two", destination="Kyoto")
    await SUPERVISOR.plan(state)
    assert state["trip_constraints"]["trip_days"] == 4
    assert state["trip_constraints"]["nights"] == 3
