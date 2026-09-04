"""Graph routing.

Two decisions live here: where a run enters the graph (a fresh plan, a
revision, or a finalisation after approval), and which specialist agents the
specialist node actually executes. Both read the state and nothing else.
"""

from __future__ import annotations

from app.core.constants import (
    AGENT_EXECUTION_ORDER,
    REVIEW_APPROVED,
    REVIEW_CHANGES_REQUESTED,
)
from app.graph.state import TravelState

ENTRY_PLAN = "plan"
ENTRY_REVISE = "revise"
ENTRY_FINALISE = "finalise"


def entry_router(state: TravelState) -> str:
    """Choose the branch a graph run starts on."""
    status = state.get("human_review_status")
    if status == REVIEW_APPROVED:
        return ENTRY_FINALISE
    if status == REVIEW_CHANGES_REQUESTED:
        return ENTRY_REVISE
    return ENTRY_PLAN


def agents_to_run(state: TravelState) -> list[str]:
    """Selected agents, in dependency order."""
    selected = set(state.get("selected_agents") or [])
    return [agent for agent in AGENT_EXECUTION_ORDER if agent in selected]


def should_finalise(state: TravelState) -> str:
    """After a review decision, either finalise or wait for the traveller."""
    if state.get("human_review_status") == REVIEW_APPROVED:
        return "final_response"
    return "await_review"


def after_review(state: TravelState) -> str:
    """Where the run goes once the human_review interrupt has resolved.

    Read after `interrupt()` returns, so `human_review_status` already carries
    the traveller's decision. Anything unrecognised ends the run with the
    journey still awaiting review, which is the safe reading: a decision
    nobody made must not finalise a journey.
    """
    status = state.get("human_review_status")
    if status == REVIEW_APPROVED:
        return "final_response"
    if status == REVIEW_CHANGES_REQUESTED:
        return "supervisor_revision"
    return "await_review"
