"""Shared TravelState.

Every agent reads from and writes to this single structure. Agents never call
each other directly: the Supervisor decides who runs, and the state carries
the result forward. That is what makes selective re-execution possible - an
agent whose slice of the state is untouched simply keeps its previous output.

The state is a ``TypedDict`` rather than a Pydantic model because LangGraph
checkpoints it to PostgreSQL between the draft and the human review, and plain
JSON-compatible structures survive that round trip unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from app.core.constants import (
    DEFAULT_LANGUAGE,
    REVIEW_PENDING,
    TRIP_DRAFT,
)


class TravelState(TypedDict, total=False):
    """The shared context passed between every JourneyMesh node."""

    # ---- request ---------------------------------------------------------
    user_query: str
    trip_constraints: dict[str, Any]
    response_language: str

    # ---- supervisor decisions -------------------------------------------
    selected_agents: list[str]
    execution_reason: str
    change_scope: list[str]
    agents_run: list[str]

    # ---- specialist results ---------------------------------------------
    flight_results: dict[str, Any]
    hotel_results: dict[str, Any]
    weather_info: dict[str, Any]
    budget_analysis: dict[str, Any]
    itinerary_plan: dict[str, Any]
    final_response: dict[str, Any]

    # ---- quality and safety ---------------------------------------------
    provider_status: list[dict[str, Any]]
    evaluation_results: dict[str, Any]
    guardrail_results: list[dict[str, Any]]

    # ---- human in the loop ----------------------------------------------
    human_review_status: str
    requested_changes: str | None
    revision_count: int
    review_iteration: int
    trip_status: str

    # ---- conversation and telemetry -------------------------------------
    messages: list[dict[str, Any]]
    llm_calls: int
    tool_calls: int
    errors: list[str]

    # ---- identity --------------------------------------------------------
    trip_id: str
    session_id: str | None
    request_id: str | None
    created_at: str
    updated_at: str


# Slice of the state each specialist agent owns. Used by selective
# re-execution so that untouched results are preserved verbatim.
AGENT_STATE_KEYS: dict[str, str] = {
    "flight_agent": "flight_results",
    "hotel_agent": "hotel_results",
    "weather_agent": "weather_info",
    "budget_agent": "budget_analysis",
    "itinerary_agent": "itinerary_plan",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_state(
    *,
    trip_id: str,
    user_query: str,
    trip_constraints: dict[str, Any],
    session_id: str | None = None,
    request_id: str | None = None,
    response_language: str = DEFAULT_LANGUAGE,
) -> TravelState:
    """Create an empty state for a brand new journey."""
    timestamp = _now()
    return TravelState(
        user_query=user_query,
        trip_constraints=trip_constraints,
        response_language=response_language,
        selected_agents=[],
        execution_reason="",
        change_scope=[],
        agents_run=[],
        flight_results={},
        hotel_results={},
        weather_info={},
        budget_analysis={},
        itinerary_plan={},
        final_response={},
        provider_status=[],
        evaluation_results={},
        guardrail_results=[],
        human_review_status=REVIEW_PENDING,
        requested_changes=None,
        revision_count=1,
        review_iteration=0,
        trip_status=TRIP_DRAFT,
        messages=[],
        llm_calls=0,
        tool_calls=0,
        errors=[],
        trip_id=trip_id,
        session_id=session_id,
        request_id=request_id,
        created_at=timestamp,
        updated_at=timestamp,
    )


def touch(state: TravelState) -> TravelState:
    state["updated_at"] = _now()
    return state


def add_message(
    state: TravelState, *, role: str, content: str, agent: str | None = None
) -> None:
    """Append a safe execution note. Never store model chain-of-thought here."""
    messages = state.setdefault("messages", [])
    messages.append(
        {
            "role": role,
            "agent": agent,
            "content": content,
            "revision": state.get("revision_count", 1),
            "at": _now(),
        }
    )
    if len(messages) > 200:
        del messages[:-200]


def add_provider_status(state: TravelState, status: dict[str, Any]) -> None:
    statuses = state.setdefault("provider_status", [])
    statuses.append(status)


def add_guardrail_result(state: TravelState, result: dict[str, Any]) -> None:
    results = state.setdefault("guardrail_results", [])
    results.append(result)


def record_error(state: TravelState, message: str) -> None:
    errors = state.setdefault("errors", [])
    if message not in errors:
        errors.append(message)


# The field that has to carry content before an agent's slice counts as a
# result. A payload such as ``{"options": []}`` means the agent ran and found
# nothing, which is not something worth preserving across a revision.
AGENT_RESULT_MARKERS: dict[str, str] = {
    "flight_results": "options",
    "hotel_results": "options",
    "weather_info": "forecast",
    "budget_analysis": "breakdown",
    "itinerary_plan": "days",
}


def has_result(state: TravelState, agent: str) -> bool:
    """True when the agent already has usable output in the state."""
    key = AGENT_STATE_KEYS.get(agent)
    if key is None:
        return False
    payload = state.get(key)
    if not payload:
        return False
    if isinstance(payload, dict):
        marker = AGENT_RESULT_MARKERS.get(key)
        if marker and marker in payload:
            return bool(payload[marker])
        return any(bool(value) for value in payload.values())
    return True


def preserved_agents(state: TravelState, selected: list[str]) -> list[str]:
    """Agents whose earlier output is carried forward unchanged."""
    return [
        agent
        for agent in AGENT_STATE_KEYS
        if agent not in selected and has_result(state, agent)
    ]


def clear_results(state: TravelState, agents: list[str]) -> None:
    """Drop the state slice owned by each listed agent."""
    for agent in agents:
        key = AGENT_STATE_KEYS.get(agent)
        if key:
            state[key] = {}  # type: ignore[literal-required]


def snapshot(state: TravelState) -> dict[str, Any]:
    """A JSON-safe copy suitable for persistence or an API response."""
    return {key: value for key, value in state.items()}


def constraint(state: TravelState, name: str, default: Any = None) -> Any:
    return (state.get("trip_constraints") or {}).get(name, default)
