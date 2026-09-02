"""The shared TravelState."""

from __future__ import annotations

from app.graph.state import (
    AGENT_STATE_KEYS,
    add_message,
    add_provider_status,
    clear_results,
    constraint,
    has_result,
    new_state,
    preserved_agents,
    record_error,
)


def build():
    return new_state(
        trip_id="trip-1",
        user_query="Plan a trip to Kyoto",
        trip_constraints={"destination": "Kyoto", "travelers": 2},
        session_id="session-1",
        response_language="bn",
    )


def test_a_new_state_starts_empty_but_complete():
    state = build()
    assert state["trip_id"] == "trip-1"
    assert state["response_language"] == "bn"
    assert state["revision_count"] == 1
    assert state["human_review_status"] == "pending"
    for key in AGENT_STATE_KEYS.values():
        assert state[key] == {}


def test_every_agent_owns_exactly_one_slice():
    assert set(AGENT_STATE_KEYS) == {
        "flight_agent",
        "hotel_agent",
        "weather_agent",
        "budget_agent",
        "itinerary_agent",
    }
    assert len(set(AGENT_STATE_KEYS.values())) == 5


def test_results_are_tracked_and_preserved():
    state = build()
    assert not has_result(state, "hotel_agent")

    state["hotel_results"] = {"options": [{"name": "A stay"}]}
    state["flight_results"] = {"options": []}
    assert has_result(state, "hotel_agent")
    assert not has_result(state, "flight_agent")

    assert preserved_agents(state, ["flight_agent"]) == ["hotel_agent"]

    clear_results(state, ["hotel_agent"])
    assert not has_result(state, "hotel_agent")


def test_messages_provider_status_and_errors_accumulate():
    state = build()
    add_message(state, role="agent", content="Hotel shortlist ready", agent="hotel_agent")
    add_provider_status(state, {"provider": "search_mcp", "ok": True})
    record_error(state, "weather_agent failed")
    record_error(state, "weather_agent failed")

    assert len(state["messages"]) == 1
    assert state["messages"][0]["agent"] == "hotel_agent"
    assert len(state["provider_status"]) == 1
    assert state["errors"] == ["weather_agent failed"]


def test_constraint_lookup_has_a_default():
    state = build()
    assert constraint(state, "destination") == "Kyoto"
    assert constraint(state, "budget", 0) == 0
