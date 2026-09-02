"""The evaluation module."""

from __future__ import annotations

import pytest

from app.evaluation import metrics
from app.evaluation.evaluator import Evaluator
from app.evaluation.rules import (
    budget_arithmetic,
    date_consistency,
    groundedness,
    itinerary_feasibility,
    language_correctness,
    schema_validity,
)
from app.evaluation.schemas import DIMENSIONS, EvaluationCheck


@pytest.mark.asyncio
async def test_a_complete_journey_scores_well(workflow, family_request):
    state = await workflow.plan(trip_id="eval-trip", request=family_request)
    result = await Evaluator().evaluate(state)

    assert result.mode == "deterministic"
    assert result.overall_score >= 0.7
    assert result.passed
    assert not result.failures
    assert set(result.dimension_scores) <= set(DIMENSIONS)


@pytest.mark.asyncio
async def test_every_dimension_is_covered_by_at_least_one_check(workflow, family_request):
    state = await workflow.plan(trip_id="eval-cover", request=family_request)
    result = await Evaluator().evaluate(state)
    covered = {check.dimension for check in result.checks}
    assert set(DIMENSIONS) <= covered


def test_budget_arithmetic_detects_a_mismatch():
    state = {
        "budget_analysis": {
            "breakdown": {
                "flights": 100,
                "hotels": 100,
                "food": 0,
                "transport": 0,
                "activities": 0,
                "miscellaneous": 0,
            },
            "estimated_total": 500,
            "total_budget": 1000,
            "remaining_budget": 500,
            "budget_status": "within_budget",
        }
    }
    check = budget_arithmetic(state)  # type: ignore[arg-type]
    assert check.outcome == "fail"


def test_date_consistency_detects_a_reversed_range():
    state = {
        "trip_constraints": {"departure_date": "2027-05-10", "return_date": "2027-05-02"},
        "itinerary_plan": {"days": []},
    }
    check = date_consistency(state)  # type: ignore[arg-type]
    assert check.outcome == "fail"


def test_groundedness_requires_a_provenance_label():
    state = {
        "flight_results": {
            "options": [{"price_per_traveler": 300, "price_source": "made_up", "airline": "X"}]
        }
    }
    check = groundedness(state)  # type: ignore[arg-type]
    assert check.outcome == "fail"


def test_itinerary_feasibility_flags_an_overloaded_day():
    state = {
        "itinerary_plan": {
            "days": [
                {
                    "day": 1,
                    "slots": [
                        {
                            "slot": "morning",
                            "travel_time_minutes": 60,
                            "activities": [{"title": "A", "duration_minutes": 900}],
                        }
                    ],
                }
            ]
        }
    }
    check = itinerary_feasibility(state)  # type: ignore[arg-type]
    assert check.outcome in {"warn", "fail"}


def test_language_correctness_detects_the_wrong_script():
    state = {
        "trip_constraints": {"response_language": "bn"},
        "final_response": {
            "overview": {"title": "A journey to Singapore", "headline": "A family plan"},
            "closing_note": "Safe travels.",
            "travel_tips": [],
        },
    }
    check = language_correctness(state)  # type: ignore[arg-type]
    assert check.outcome == "fail"


def test_schema_validity_rejects_a_malformed_slice():
    state = {"budget_analysis": {"breakdown": {"flights": "a lot"}}}
    check = schema_validity(state)  # type: ignore[arg-type]
    assert check.outcome == "fail"


def test_metrics_weight_dimensions():
    checks = [
        EvaluationCheck(name="a", dimension="safety", outcome="pass", score=1.0),
        EvaluationCheck(
            name="b",
            dimension="relevance",
            outcome="warn",
            score=0.5,
            reason="only half the interests were covered",
        ),
        EvaluationCheck(name="c", dimension="relevance", outcome="skipped", score=0.0),
    ]
    scores = metrics.dimension_scores(checks)
    assert scores == {"safety": 1.0, "relevance": 0.5}
    assert 0.5 < metrics.overall_score(checks) < 1.0
    assert metrics.warnings(checks)


def test_a_safety_failure_blocks_the_result():
    checks = [
        EvaluationCheck(
            name="safety", dimension="safety", outcome="fail", score=0.0, reason="blocked"
        )
    ]
    assert metrics.blocking_failures(checks)
