"""Tool authorization policy for the MCP Tool Guard.

A tool that is not listed here cannot be called - the guard denies by
default. Operations are classified so that anything beyond reading and
searching requires an explicit human confirmation.
"""

from __future__ import annotations

from typing import Any, Literal

from app.core.constants import (
    FLIGHT_AGENT,
    HOTEL_AGENT,
    ITINERARY_AGENT,
    WEATHER_AGENT,
)

Operation = Literal["read", "search", "write", "destructive"]
Risk = Literal["low", "medium", "high"]

OPERATION_ORDER: dict[str, int] = {"read": 0, "search": 1, "write": 2, "destructive": 3}

# Operations JourneyMesh performs today without human confirmation.
AUTONOMOUS_OPERATIONS = ("read", "search")


class ToolPolicy(dict):
    """A plain dict subclass so policies stay JSON-serialisable."""


TOOL_POLICIES: dict[str, dict[str, Any]] = {
    # ---- Aviation -------------------------------------------------------
    "search_flights": {
        "allowed_agents": [FLIGHT_AGENT],
        "operation": "search",
        "risk": "low",
        "requires_confirmation": False,
        "max_calls_per_run": 4,
        "argument_schema": {
            "origin": {"type": "string", "required": True, "max_length": 120},
            "destination": {"type": "string", "required": True, "max_length": 120},
            "departure_date": {"type": "string", "required": False, "max_length": 10},
            "return_date": {"type": "string", "required": False, "max_length": 10},
            "travelers": {"type": "integer", "required": False, "min": 1, "max": 20},
        },
    },
    "lookup_airport": {
        "allowed_agents": [FLIGHT_AGENT],
        "operation": "read",
        "risk": "low",
        "requires_confirmation": False,
        "max_calls_per_run": 8,
        "argument_schema": {
            "city": {"type": "string", "required": True, "max_length": 120},
        },
    },
    # ---- Search ---------------------------------------------------------
    "search_hotels": {
        "allowed_agents": [HOTEL_AGENT],
        "operation": "search",
        "risk": "low",
        "requires_confirmation": False,
        "max_calls_per_run": 4,
        "argument_schema": {
            "destination": {"type": "string", "required": True, "max_length": 120},
            "max_price_per_night": {"type": "number", "required": False, "min": 0},
            "travel_style": {"type": "string", "required": False, "max_length": 32},
            "travelers": {"type": "integer", "required": False, "min": 1, "max": 20},
        },
    },
    "web_search": {
        "allowed_agents": [HOTEL_AGENT, ITINERARY_AGENT],
        "operation": "search",
        "risk": "low",
        "requires_confirmation": False,
        "max_calls_per_run": 6,
        "argument_schema": {
            "query": {"type": "string", "required": True, "max_length": 400},
            "max_results": {"type": "integer", "required": False, "min": 1, "max": 10},
        },
    },
    # ---- Weather --------------------------------------------------------
    "get_current_weather": {
        "allowed_agents": [WEATHER_AGENT],
        "operation": "read",
        "risk": "low",
        "requires_confirmation": False,
        "max_calls_per_run": 3,
        "argument_schema": {
            "location": {"type": "string", "required": True, "max_length": 120},
        },
    },
    "get_weather_forecast": {
        "allowed_agents": [WEATHER_AGENT],
        "operation": "read",
        "risk": "low",
        "requires_confirmation": False,
        "max_calls_per_run": 3,
        "argument_schema": {
            "location": {"type": "string", "required": True, "max_length": 120},
            "days": {"type": "integer", "required": False, "min": 1, "max": 14},
        },
    },
    # ---- Future write operations ---------------------------------------
    # These are declared so the policy surface is explicit. They are not
    # wired to any provider yet and always require confirmation.
    "book_flight": {
        "allowed_agents": [FLIGHT_AGENT],
        "operation": "write",
        "risk": "high",
        "requires_confirmation": True,
        "enabled": False,
        "argument_schema": {},
    },
    "book_hotel": {
        "allowed_agents": [HOTEL_AGENT],
        "operation": "write",
        "risk": "high",
        "requires_confirmation": True,
        "enabled": False,
        "argument_schema": {},
    },
    "cancel_reservation": {
        "allowed_agents": [FLIGHT_AGENT, HOTEL_AGENT],
        "operation": "destructive",
        "risk": "high",
        "requires_confirmation": True,
        "enabled": False,
        "argument_schema": {},
    },
}

# Arguments that must never be forwarded to an external tool.
FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "authorization",
        "password",
        "secret",
        "passport",
        "passport_number",
        "national_id",
        "credit_card",
        "card_number",
        "cvv",
        "database_url",
    }
)


def get_policy(tool_name: str) -> dict[str, Any] | None:
    return TOOL_POLICIES.get(tool_name)


def is_enabled(tool_name: str) -> bool:
    policy = get_policy(tool_name)
    return bool(policy) and policy.get("enabled", True)


def allowlisted_tools() -> list[str]:
    return [name for name, policy in TOOL_POLICIES.items() if policy.get("enabled", True)]


def tools_for_agent(agent: str) -> list[str]:
    return [
        name
        for name, policy in TOOL_POLICIES.items()
        if policy.get("enabled", True) and agent in policy.get("allowed_agents", [])
    ]
