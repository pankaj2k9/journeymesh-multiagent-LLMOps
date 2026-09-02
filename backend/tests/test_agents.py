"""Specialist agent behaviour."""

from __future__ import annotations

import pytest

from app.agents import (
    BudgetAgent,
    FinalResponseAgent,
    FlightAgent,
    HotelAgent,
    ItineraryAgent,
    WeatherAgent,
)
from app.graph.state import new_state
from app.mcp.client import MCPClient

CONSTRAINTS = {
    "origin": "Dhaka",
    "destination": "Singapore",
    "departure_date": "2027-01-10",
    "return_date": "2027-01-14",
    "travelers": 3,
    "budget": 3000,
    "currency": "USD",
    "travel_style": "family",
    "interests": ["food", "nature", "family_activities"],
    "nights": 4,
    "trip_days": 5,
    "response_language": "en",
}


def make_state(**overrides):
    constraints = {**CONSTRAINTS, **overrides}
    return new_state(
        trip_id="test-trip",
        user_query="Plan a 5-day family trip from Dhaka to Singapore",
        trip_constraints=constraints,
        response_language=constraints.get("response_language", "en"),
    )


@pytest.mark.asyncio
async def test_flight_agent_produces_labelled_options():
    state = make_state()
    await FlightAgent(mcp_client=MCPClient()).run(state)

    flights = state["flight_results"]
    assert flights["options"]
    assert flights["origin_airports"][0]["iata"] == "DAC"
    for option in flights["options"]:
        assert option["price_source"] in {"LIVE", "SEARCH_DERIVED", "ESTIMATE", "UNAVAILABLE"}
    assert not state["errors"]


@pytest.mark.asyncio
async def test_flight_agent_explains_a_missing_origin():
    state = make_state(origin=None)
    await FlightAgent(mcp_client=MCPClient()).run(state)
    assert state["flight_results"]["source"] == "UNAVAILABLE"
    assert state["flight_results"]["notes"]


@pytest.mark.asyncio
async def test_hotel_agent_ranks_within_the_budget():
    state = make_state()
    await HotelAgent(mcp_client=MCPClient()).run(state)

    hotels = state["hotel_results"]
    assert hotels["options"]
    ceiling = hotels["price_ceiling_per_night"]
    assert ceiling and hotels["options"][0]["price_per_night"] <= ceiling * 1.05


@pytest.mark.asyncio
async def test_hotel_agent_honours_an_explicit_nightly_ceiling():
    state = make_state(max_hotel_price_per_night=70)
    await HotelAgent(mcp_client=MCPClient()).run(state)
    top = state["hotel_results"]["options"][0]
    assert top["price_per_night"] <= 70


@pytest.mark.asyncio
async def test_weather_agent_returns_a_forecast_for_the_trip_length():
    state = make_state()
    await WeatherAgent(mcp_client=MCPClient()).run(state)

    weather = state["weather_info"]
    assert len(weather["forecast"]) == 5
    assert weather["packing_recommendations"]
    assert weather["suggestion_codes"] is not None


@pytest.mark.asyncio
async def test_budget_agent_separates_confirmed_from_estimated_costs():
    state = make_state()
    mcp = MCPClient()
    await FlightAgent(mcp_client=mcp).run(state)
    await HotelAgent(mcp_client=mcp).run(state)
    await BudgetAgent(mcp_client=mcp).run(state)

    budget = state["budget_analysis"]
    breakdown = budget["breakdown"]
    computed = round(
        sum(
            breakdown[key]
            for key in ("flights", "hotels", "food", "transport", "activities", "miscellaneous")
        ),
        2,
    )
    assert abs(budget["estimated_total"] - computed) < 0.01
    assert budget["budget_status"] in {
        "within_budget",
        "near_limit",
        "over_budget",
        "insufficient_data",
    }
    assert set(budget["line_provenance"]) >= {"flights", "hotels", "food"}


@pytest.mark.asyncio
async def test_budget_agent_reports_missing_budget_honestly():
    state = make_state(budget=None)
    await BudgetAgent(mcp_client=MCPClient()).run(state)
    assert state["budget_analysis"]["budget_status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_itinerary_agent_builds_one_day_per_trip_day():
    state = make_state()
    mcp = MCPClient()
    await WeatherAgent(mcp_client=mcp).run(state)
    await ItineraryAgent(mcp_client=mcp).run(state)

    plan = state["itinerary_plan"]
    assert plan["total_days"] == 5
    assert len(plan["days"]) == 5
    assert all(day["slots"] for day in plan["days"])
    assert plan["days"][0]["slots"][0]["activities"][0]["title"] == "Arrival and check-in"


@pytest.mark.asyncio
async def test_itinerary_avoids_the_outdoors_when_rain_is_likely():
    state = make_state()
    mcp = MCPClient()
    await WeatherAgent(mcp_client=mcp).run(state)
    state["weather_info"]["forecast"][1]["precipitation_chance_pct"] = 95
    await ItineraryAgent(mcp_client=mcp).run(state)

    second_day = state["itinerary_plan"]["days"][1]
    indoor = [
        activity["indoor"]
        for slot in second_day["slots"]
        for activity in slot["activities"]
    ]
    assert any(indoor)


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "bn", "hi"])
async def test_final_response_agent_writes_in_the_requested_language(language):
    state = make_state(response_language=language)
    mcp = MCPClient()
    for agent in (FlightAgent, HotelAgent, WeatherAgent, BudgetAgent, ItineraryAgent):
        await agent(mcp_client=mcp).run(state)
    await FinalResponseAgent(mcp_client=mcp).run(state)

    final = state["final_response"]
    assert final["language"] == language
    title = final["overview"]["title"]
    if language == "bn":
        assert any("ঀ" <= char <= "৿" for char in title)
    elif language == "hi":
        assert any("ऀ" <= char <= "ॿ" for char in title)
    else:
        assert "journey" in title.lower()
