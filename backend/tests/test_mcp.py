"""MCP registry, configuration and client dispatch."""

from __future__ import annotations

import pytest

from app.core.exceptions import ToolAuthorizationError
from app.mcp import registry
from app.mcp.client import MCPClient
from app.mcp.config import server_configs


def test_every_registered_tool_has_a_policy():
    from app.guardrails.policies import TOOL_POLICIES

    for descriptor in registry.discover():
        assert descriptor.name in TOOL_POLICIES, descriptor.name


def test_the_catalogue_describes_transports():
    catalogue = registry.catalogue()
    names = {entry["tool"] for entry in catalogue}
    assert {"search_flights", "search_hotels", "get_weather_forecast"} <= names
    assert set(server_configs()) == {"aviation", "search", "weather"}


@pytest.mark.asyncio
async def test_a_permitted_tool_call_returns_normalised_data():
    client = MCPClient()
    result = await client.call(
        "search_flights",
        agent="flight_agent",
        arguments={"origin": "Dhaka", "destination": "Singapore", "travelers": 2},
    )
    assert result.ok
    assert result.data["options"]
    assert result.data["source"] in {"LIVE", "ESTIMATE"}


@pytest.mark.asyncio
async def test_a_blocked_tool_call_returns_a_decision_not_an_exception():
    client = MCPClient()
    result = await client.call(
        "search_flights",
        agent="itinerary_agent",
        arguments={"origin": "Dhaka", "destination": "Singapore"},
    )
    assert not result.ok
    assert result.blocked
    assert result.decision is not None and result.decision.rule == "agent_not_authorized"


@pytest.mark.asyncio
async def test_a_blocked_tool_call_can_raise_when_asked_to():
    client = MCPClient()
    with pytest.raises(ToolAuthorizationError):
        await client.call(
            "search_hotels",
            agent="flight_agent",
            arguments={"destination": "Singapore"},
            raise_on_block=True,
        )


@pytest.mark.asyncio
async def test_weather_tools_return_a_labelled_forecast():
    client = MCPClient()
    result = await client.call(
        "get_weather_forecast",
        agent="weather_agent",
        arguments={"location": "Singapore", "days": 4},
    )
    assert result.ok
    assert len(result.data["forecast"]) == 4
    assert result.data["source"] in {"LIVE", "ESTIMATE"}
    assert result.data["packing_codes"]


@pytest.mark.asyncio
async def test_hotel_search_respects_a_nightly_ceiling():
    client = MCPClient()
    result = await client.call(
        "search_hotels",
        agent="hotel_agent",
        arguments={"destination": "Singapore", "max_price_per_night": 90, "travelers": 2},
    )
    assert result.ok
    prices = [option["price_per_night"] for option in result.data["options"] if option["price_per_night"]]
    assert prices and min(prices) <= 90


def test_airport_lookup_resolves_known_cities():
    from app.mcp.aviation import lookup_airport

    assert lookup_airport("Dhaka")["iata"] == "DAC"
    assert lookup_airport("Singapore")["iata"] == "SIN"
    assert lookup_airport("Atlantis")["iata"] is None
