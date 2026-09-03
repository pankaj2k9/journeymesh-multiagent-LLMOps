"""Supervisor Agent.

The Supervisor answers one question: *which specialist agents does this
request actually need?* It never plans the trip itself. On the first pass it
reads the request; on a revision it reads the requested change and selects
only the agents affected by it, plus their dependents.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any

from app.core.constants import (
    AGENT_DEPENDENTS,
    AGENT_EXECUTION_ORDER,
    BUDGET_AGENT,
    FLIGHT_AGENT,
    HOTEL_AGENT,
    ITINERARY_AGENT,
    SPECIALIST_AGENTS,
    WEATHER_AGENT,
)
from app.graph.state import TravelState, add_message, has_result
from app.observability.logging import get_logger
from app.observability.tracing import span
from app.services.llm_service import LLMService, get_llm_service

logger = get_logger("journeymesh.agents.supervisor")

# ---- Intent vocabulary ---------------------------------------------------
_FLIGHT_TERMS = (
    "flight", "flights", "fly", "flying", "airline", "airfare", "airport",
    "departure", "layover", "nonstop", "non-stop", "red-eye", "boarding",
)
_HOTEL_TERMS = (
    "hotel", "hotels", "stay", "staying", "accommodation", "accomodation",
    "hostel", "resort", "airbnb", "guesthouse", "room", "rooms", "lodging",
    "check-in", "checkin",
)
_WEATHER_TERMS = (
    "weather", "forecast", "rain", "raining", "temperature", "climate",
    "monsoon", "snow", "humid", "sunny", "storm", "hot", "cold", "pack",
    "packing",
)
_BUDGET_TERMS = (
    "budget", "cost", "costs", "price", "prices", "cheap", "cheaper",
    "expensive", "afford", "spend", "spending", "money", "under $", "per night",
    "total", "save",
)
_ITINERARY_TERMS = (
    "itinerary", "plan", "planning", "schedule", "day-by-day", "day by day",
    "activities", "things to do", "sightseeing", "tour", "visit", "attractions",
    "days in", "trip to", "travel to",
)
# Phrases that mean "the whole journey", not merely "I would like a plan".
# "plan a" is how almost every request opens, so it is deliberately absent: it
# would make every request a full-team request and defeat the point of having
# a supervisor choose.
_FULL_TRIP_TERMS = (
    "complete", "full trip", "complete trip", "whole trip", "entire trip",
    "everything", "end to end", "end-to-end",
)

_PRICE_CEILING = re.compile(
    r"(?:under|below|less than|max(?:imum)?|no more than|within)\s*"
    r"(?:us)?\$?\s*(\d[\d,]*)(?:\s*(?:usd|dollars))?",
    re.IGNORECASE,
)
_PER_NIGHT = re.compile(r"per\s*night|a\s*night|/\s*night|nightly", re.IGNORECASE)

# "a 5-day trip", "four days in Kyoto", "3 nights"
_DAYS_IN_TEXT = re.compile(r"\b(\d{1,2})\s*[- ]?\s*day(?:s)?\b", re.IGNORECASE)
_NIGHTS_IN_TEXT = re.compile(r"\b(\d{1,2})\s*[- ]?\s*night(?:s)?\b", re.IGNORECASE)
_WORD_NUMBERS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_WORD_DAYS = re.compile(
    r"\b(" + "|".join(_WORD_NUMBERS) + r")\s*[- ]?\s*(day|night)s?\b", re.IGNORECASE
)


def duration_from_text(text: str) -> tuple[int | None, int | None]:
    """Read a trip length out of free text. Returns (trip_days, nights)."""
    match = _DAYS_IN_TEXT.search(text or "")
    if match:
        days = int(match.group(1))
        if 1 <= days <= 30:
            return days, max(days - 1, 0)

    match = _NIGHTS_IN_TEXT.search(text or "")
    if match:
        nights = int(match.group(1))
        if 1 <= nights <= 30:
            return nights + 1, nights

    match = _WORD_DAYS.search(text or "")
    if match:
        value = _WORD_NUMBERS[match.group(1).lower()]
        if match.group(2).lower() == "night":
            return value + 1, value
        return value, max(value - 1, 0)

    return None, None

# "keep my flights", "don't change the hotel", "leave the weather as is" - the
# traveller is naming something they do NOT want re-run.
_PRESERVE = re.compile(
    r"\b(?:keep|retain|leave|don'?t\s+change|do\s+not\s+change|no\s+change\s+to|"
    r"same|unchanged|as\s+is)\b[^.!?]{0,40}?\b"
    r"(flight|flights|hotel|hotels|stay|accommodation|weather|forecast|budget|"
    r"itinerary|activities|plan)\b",
    re.IGNORECASE,
)

_PRESERVE_TARGETS = {
    "flight": FLIGHT_AGENT,
    "flights": FLIGHT_AGENT,
    "hotel": HOTEL_AGENT,
    "hotels": HOTEL_AGENT,
    "stay": HOTEL_AGENT,
    "accommodation": HOTEL_AGENT,
    "weather": WEATHER_AGENT,
    "forecast": WEATHER_AGENT,
    "budget": BUDGET_AGENT,
    "itinerary": ITINERARY_AGENT,
    "activities": ITINERARY_AGENT,
    "plan": ITINERARY_AGENT,
}


def preservation_requests(text: str) -> set[str]:
    """Agents the traveller explicitly asked JourneyMesh to leave alone."""
    return {
        _PRESERVE_TARGETS[match.group(1).lower()]
        for match in _PRESERVE.finditer(text or "")
        if match.group(1).lower() in _PRESERVE_TARGETS
    }


@cache
def _vocabulary(terms: tuple[str, ...]) -> re.Pattern[str]:
    """Compile an intent vocabulary into one word-boundary pattern.

    Substring matching is wrong here and was wrong in practice: "hotels"
    contains "hot", so every request mentioning a hotel also looked like a
    question about the weather and pulled in an agent nobody asked for. The
    lookarounds are used instead of ``\b`` because several terms end in a
    non-word character - "under $", "/ night" - where ``\b`` would not apply.
    """
    alternatives = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def _mentions(text: str, terms: tuple[str, ...]) -> bool:
    return bool(_vocabulary(terms).search(text or ""))


def _ordered(agents: set[str]) -> list[str]:
    return [agent for agent in AGENT_EXECUTION_ORDER if agent in agents]


def expand_dependents(agents: set[str]) -> set[str]:
    """Add every agent whose output depends on one that is re-running."""
    expanded = set(agents)
    changed = True
    while changed:
        changed = False
        for agent in list(expanded):
            for dependent in AGENT_DEPENDENTS.get(agent, ()):  # type: ignore[arg-type]
                if dependent not in expanded:
                    expanded.add(dependent)
                    changed = True
    return expanded


class SupervisorAgent:
    """Dynamic agent selection for both the first pass and revisions."""

    name = "supervisor"

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or get_llm_service()

    # ---- first pass ------------------------------------------------------
    async def plan(self, state: TravelState) -> TravelState:
        """Decide which agents run for a fresh request."""
        with span("agent:supervisor", kind="agent"):
            query = state.get("user_query", "") or ""
            constraints = dict(state.get("trip_constraints") or {})

            # A request without dates often still states its length in words.
            if not constraints.get("trip_days"):
                days, nights = duration_from_text(query)
                if days:
                    constraints["trip_days"] = days
                    constraints.setdefault("nights", nights)
                    state["trip_constraints"] = constraints

            selected, reason = self._select_for_request(query, constraints)
            refined = await self._refine_with_model(query, constraints, selected)
            if refined:
                selected, reason = refined

            state["selected_agents"] = _ordered(set(selected))
            state["execution_reason"] = reason
            state["change_scope"] = []
            add_message(
                state,
                role="supervisor",
                content=(
                    f"Selected {len(state['selected_agents'])} specialist agent(s): "
                    f"{', '.join(state['selected_agents'])}. {reason}"
                ),
                agent=self.name,
            )
            state["llm_calls"] = self.llm.usage.count
        return state

    def _select_for_request(
        self, query: str, constraints: dict[str, Any]
    ) -> tuple[list[str], str]:
        selected: set[str] = set()
        reasons: list[str] = []

        has_destination = bool(constraints.get("destination"))
        has_dates = bool(constraints.get("departure_date"))
        has_budget = constraints.get("budget") is not None
        has_origin = bool(constraints.get("origin"))

        # A narrow question gets a narrow answer.
        if _mentions(query, _WEATHER_TERMS):
            selected.add(WEATHER_AGENT)
            reasons.append("the request asks about conditions at the destination")
        if _mentions(query, _FLIGHT_TERMS) or has_origin:
            selected.add(FLIGHT_AGENT)
            reasons.append("the request involves getting there")
        if _mentions(query, _HOTEL_TERMS):
            selected.add(HOTEL_AGENT)
            reasons.append("the request involves where to stay")
        if _mentions(query, _BUDGET_TERMS) or has_budget:
            selected.add(BUDGET_AGENT)
            reasons.append("a budget constraint has to be respected")
        if _mentions(query, _ITINERARY_TERMS) or (has_destination and has_dates):
            selected.add(ITINERARY_AGENT)
            reasons.append("a day-by-day plan is expected")

        # A full-journey request needs the whole team - except the forecast,
        # which stays opt-in. "Complete" describes the plan, not a request for
        # weather data, and retrieving a forecast nobody asked for costs a
        # provider call and puts a section on the page that was not wanted.
        if _mentions(query, _FULL_TRIP_TERMS) and has_destination:
            selected.update(
                agent for agent in SPECIALIST_AGENTS if agent != WEATHER_AGENT
            )
            reasons.append("the request covers a complete journey")

        # An itinerary needs somewhere to stay, and it needs a cost picture when
        # the traveller stated a budget. It does not need a forecast: weather is
        # only retrieved when it was actually asked for, so a request that never
        # mentions it does not spend a provider call on it.
        if ITINERARY_AGENT in selected:
            if has_budget:
                selected.add(BUDGET_AGENT)
            if has_destination and (constraints.get("nights") or 0) >= 1:
                selected.add(HOTEL_AGENT)

        # Budget cannot be assessed without the two largest cost lines. Getting
        # there is one of them whether or not an origin was typed - the flight
        # agent resolves or estimates it - so a stated budget always pulls it in.
        if BUDGET_AGENT in selected and has_destination:
            selected.add(FLIGHT_AGENT)
            if (constraints.get("nights") or 0) >= 1:
                selected.add(HOTEL_AGENT)

        if not selected:
            # Nothing matched, but the request passed the relevance guardrail,
            # so treat it as a light planning request.
            selected.add(ITINERARY_AGENT)
            reasons.append("no specific sub-question was detected, so a plan is drafted")

        reason = "Chosen because " + "; ".join(dict.fromkeys(reasons)) + "."
        return _ordered(selected), reason

    async def _refine_with_model(
        self, query: str, constraints: dict[str, Any], heuristic: list[str]
    ) -> tuple[list[str], str] | None:
        """Let the model widen or narrow the selection when one is configured."""
        if not self.llm.available:
            return None

        system = (
            "You route travel requests to specialist agents in a planning system. "
            f"The available agents are: {', '.join(SPECIALIST_AGENTS)}. "
            "Select only the agents that are genuinely required. "
            "Return JSON with keys 'selected_agents' (array) and 'execution_reason' "
            "(one short sentence). Do not include any reasoning beyond that sentence."
        )
        user = (
            f"Request: {query}\n"
            f"Known constraints: {constraints}\n"
            f"A rule-based router proposed: {heuristic}\n"
            "Correct it if it is clearly wrong."
        )
        payload = await self.llm.complete_json(system=system, user=user, purpose="supervisor_route")
        if not payload:
            return None

        proposed = payload.get("selected_agents")
        if not isinstance(proposed, list) or not proposed:
            return None
        cleaned = {
            str(agent).strip().lower()
            for agent in proposed
            if str(agent).strip().lower() in SPECIALIST_AGENTS
        }
        if not cleaned:
            return None
        reason = str(payload.get("execution_reason") or "Selected by the routing model.")[:300]
        return _ordered(cleaned), reason

    # ---- revisions -------------------------------------------------------
    def analyse_change(self, state: TravelState, requested_changes: str) -> dict[str, Any]:
        """Decide which agents must re-run for a requested change.

        Only the agents the change actually touches are selected, together with
        the agents that depend on them. Everything else keeps its result.
        """
        text = requested_changes or ""
        lowered = text.lower()
        keep = preservation_requests(text)
        scope: set[str] = set()
        reasons: list[str] = []
        constraint_updates: dict[str, Any] = {}

        if _mentions(lowered, _HOTEL_TERMS):
            scope.add(HOTEL_AGENT)
            reasons.append("the change concerns accommodation")
        if _mentions(lowered, _FLIGHT_TERMS):
            scope.add(FLIGHT_AGENT)
            reasons.append("the change concerns flights")
        if _mentions(lowered, _WEATHER_TERMS):
            if not has_result(state, WEATHER_AGENT) or "refresh" in lowered or "update" in lowered:
                scope.add(WEATHER_AGENT)
                reasons.append("weather data has to be refreshed")
            else:
                scope.add(ITINERARY_AGENT)
                reasons.append("activities are adjusted to the weather already retrieved")
        if _mentions(lowered, _ITINERARY_TERMS) or "activity" in lowered or "activities" in lowered:
            scope.add(ITINERARY_AGENT)
            reasons.append("the daily plan changes")
        if _mentions(lowered, _BUDGET_TERMS):
            scope.add(BUDGET_AGENT)
            reasons.append("the cost picture changes")

        # A price ceiling is a hotel instruction when it is nightly, and a
        # whole-trip instruction otherwise.
        ceiling = _PRICE_CEILING.search(text)
        if ceiling:
            try:
                amount = float(ceiling.group(1).replace(",", ""))
            except ValueError:
                amount = None  # type: ignore[assignment]
            if amount:
                if _PER_NIGHT.search(text) or HOTEL_AGENT in scope:
                    constraint_updates["max_hotel_price_per_night"] = amount
                    scope.add(HOTEL_AGENT)
                    reasons.append(f"a nightly ceiling of {amount:.0f} was requested")
                else:
                    constraint_updates["budget"] = amount
                    scope.update({BUDGET_AGENT, HOTEL_AGENT, FLIGHT_AGENT})
                    reasons.append(f"a total budget of {amount:.0f} was requested")

        if not scope:
            # The change could not be attributed to one area; re-plan the day
            # structure, which is the cheapest way to honour a vague request.
            scope.add(ITINERARY_AGENT)
            reasons.append("the change was general, so the daily plan is regenerated")

        # An explicit "keep my flights" wins over a keyword match on the same word.
        if keep:
            scope -= keep
            reasons.append(
                "the traveller asked to keep " + ", ".join(sorted(keep)).replace("_", " ")
            )
            if not scope:
                scope.add(ITINERARY_AGENT)

        change_scope = _ordered(scope)
        selected = [agent for agent in _ordered(expand_dependents(scope)) if agent not in keep]

        preserved = [
            agent
            for agent in SPECIALIST_AGENTS
            if agent not in selected and has_result(state, agent)
        ]

        reason = "Re-running because " + "; ".join(dict.fromkeys(reasons)) + "."
        logger.info(
            "revision routing decided",
            extra={
                "selected_agents": selected,
                "change_scope": change_scope,
                "preserved": preserved,
            },
        )
        return {
            "selected_agents": selected,
            "change_scope": change_scope,
            "execution_reason": reason,
            "preserved_agents": preserved,
            "constraint_updates": constraint_updates,
        }

    async def plan_revision(self, state: TravelState, requested_changes: str) -> TravelState:
        """Apply a change analysis to the state."""
        analysis = self.analyse_change(state, requested_changes)

        constraints = dict(state.get("trip_constraints") or {})
        constraints.update(analysis["constraint_updates"])
        state["trip_constraints"] = constraints

        state["selected_agents"] = analysis["selected_agents"]
        state["change_scope"] = analysis["change_scope"]
        state["execution_reason"] = analysis["execution_reason"]
        state["requested_changes"] = requested_changes

        add_message(
            state,
            role="supervisor",
            content=(
                f"Revision {state.get('revision_count', 1)}: re-running "
                f"{', '.join(analysis['selected_agents']) or 'no agents'}; preserving "
                f"{', '.join(analysis['preserved_agents']) or 'nothing'}. "
                f"{analysis['execution_reason']}"
            ),
            agent=self.name,
        )
        return state
