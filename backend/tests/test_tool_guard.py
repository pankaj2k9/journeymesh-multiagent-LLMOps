"""MCP Tool Guard authorization."""

from __future__ import annotations

import pytest

from app.guardrails.tool_guard import ToolGuard


@pytest.fixture()
def guard() -> ToolGuard:
    return ToolGuard()


def test_an_authorised_agent_may_call_its_tool(guard):
    decision = guard.authorize(
        tool="search_flights",
        agent="flight_agent",
        arguments={"origin": "Dhaka", "destination": "Singapore"},
    )
    assert decision.allowed
    assert decision.operation == "search"


def test_an_unauthorised_agent_is_refused(guard):
    decision = guard.authorize(
        tool="search_flights",
        agent="hotel_agent",
        arguments={"origin": "Dhaka", "destination": "Singapore"},
    )
    assert not decision.allowed
    assert decision.rule == "agent_not_authorized"


def test_an_unknown_tool_is_refused(guard):
    decision = guard.authorize(tool="delete_everything", agent="flight_agent")
    assert not decision.allowed
    assert decision.rule == "not_allowlisted"


def test_a_write_tool_requires_confirmation(guard):
    decision = guard.authorize(tool="book_flight", agent="flight_agent", arguments={})
    assert not decision.allowed
    assert decision.rule in {"tool_disabled", "confirmation_required"}


def test_missing_required_arguments_are_refused(guard):
    decision = guard.authorize(
        tool="search_flights", agent="flight_agent", arguments={"origin": "Dhaka"}
    )
    assert not decision.allowed
    assert decision.rule == "invalid_arguments"


def test_unexpected_arguments_are_refused(guard):
    decision = guard.authorize(
        tool="get_current_weather",
        agent="weather_agent",
        arguments={"location": "Dubai", "callback": "http://evil.example"},
    )
    assert not decision.allowed
    assert decision.rule == "invalid_arguments"


def test_credentials_may_never_be_forwarded(guard):
    decision = guard.authorize(
        tool="web_search",
        agent="hotel_agent",
        arguments={"query": "hotels", "api_key": "gsk_secret_value"},
    )
    assert not decision.allowed
    assert decision.rule in {"forbidden_argument", "invalid_arguments"}


def test_the_call_budget_is_enforced(guard):
    for _ in range(3):
        assert guard.authorize(
            tool="get_current_weather", agent="weather_agent", arguments={"location": "Dubai"}
        ).allowed
    fourth = guard.authorize(
        tool="get_current_weather", agent="weather_agent", arguments={"location": "Dubai"}
    )
    assert not fourth.allowed
    assert fourth.rule == "call_budget_exceeded"


def test_personal_data_is_stripped_from_tool_arguments(guard):
    decision = guard.authorize(
        tool="web_search",
        agent="hotel_agent",
        arguments={"query": "hotel for a.traveller@example.com"},
    )
    assert decision.allowed
    assert "example.com" not in decision.sanitized_arguments["query"]
    assert "email" in decision.redactions
