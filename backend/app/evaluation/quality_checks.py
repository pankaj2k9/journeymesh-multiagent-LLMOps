"""LLM-as-judge checks.

Only subjective qualities are judged by a model - how well the plan matches
the traveller's stated preferences, and how clearly it reads. Everything a
rule can decide is decided by a rule in ``rules.py``. When no model is
configured these checks are reported as skipped rather than guessed.
"""

from __future__ import annotations

from typing import Any

from app.evaluation.schemas import EvaluationCheck
from app.graph.state import TravelState
from app.observability.logging import get_logger
from app.services.llm_service import LLMService, get_llm_service

logger = get_logger("journeymesh.evaluation.judge")

_SYSTEM = (
    "You review a generated travel plan for quality. Score each requested "
    "dimension from 0 to 1. Judge only what you are shown. Return JSON of the "
    'form {"scores": {"recommendation_relevance": 0.0, "clarity": 0.0, '
    '"preference_alignment": 0.0}, "notes": "one short sentence"}. '
    "Do not include your reasoning."
)

_DIMENSION_MAP = {
    "recommendation_relevance": "relevance",
    "clarity": "completeness",
    "preference_alignment": "relevance",
}


def _skipped(reason: str) -> list[EvaluationCheck]:
    return [
        EvaluationCheck(
            name=name,
            dimension=_DIMENSION_MAP[name],
            kind="llm_judge",
            outcome="skipped",
            score=0.0,
            weight=0.5,
            reason=reason,
        )
        for name in _DIMENSION_MAP
    ]


def _digest(state: TravelState) -> dict[str, Any]:
    """A compact, PII-free view of the plan for the judge."""
    constraints = state.get("trip_constraints") or {}
    itinerary = state.get("itinerary_plan") or {}
    hotels = state.get("hotel_results") or {}
    budget = state.get("budget_analysis") or {}
    return {
        "destination": constraints.get("destination"),
        "travelers": constraints.get("travelers"),
        "travel_style": constraints.get("travel_style"),
        "interests": constraints.get("interests"),
        "budget_status": budget.get("budget_status"),
        "estimated_total": budget.get("estimated_total"),
        "recommended_stay": (hotels.get("options") or [{}])[0].get("name"),
        "days": [
            {
                "day": day.get("day"),
                "activities": [
                    activity.get("title")
                    for slot in day.get("slots", [])
                    for activity in slot.get("activities", [])
                ],
            }
            for day in (itinerary.get("days") or [])[:7]
        ],
    }


async def judge(
    state: TravelState, llm: LLMService | None = None
) -> list[EvaluationCheck]:
    """Run the subjective checks, or report them as skipped."""
    service = llm or get_llm_service()
    if not service.available:
        return _skipped("No evaluator model is configured.")

    payload = await service.complete_json(
        system=_SYSTEM,
        user=str(_digest(state)),
        purpose="evaluation_judge",
    )
    if not payload or not isinstance(payload.get("scores"), dict):
        return _skipped("The evaluator model returned no usable score.")

    note = str(payload.get("notes") or "")[:200]
    checks: list[EvaluationCheck] = []
    for name, dimension in _DIMENSION_MAP.items():
        raw = payload["scores"].get(name)
        try:
            score = max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            checks.append(
                EvaluationCheck(
                    name=name,
                    dimension=dimension,
                    kind="llm_judge",
                    outcome="skipped",
                    weight=0.5,
                    reason="The evaluator model did not score this dimension.",
                )
            )
            continue
        checks.append(
            EvaluationCheck(
                name=name,
                dimension=dimension,
                kind="llm_judge",
                outcome="pass" if score >= 0.6 else ("warn" if score >= 0.4 else "fail"),
                score=score,
                weight=0.5,
                reason=note or "Judged by the evaluator model.",
            )
        )
    return checks
