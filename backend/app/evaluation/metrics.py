"""Score aggregation for the evaluation module."""

from __future__ import annotations

from collections.abc import Iterable

from app.evaluation.schemas import DIMENSION_WEIGHTS, EvaluationCheck


def dimension_scores(checks: Iterable[EvaluationCheck]) -> dict[str, float]:
    """Average the checks that belong to each dimension."""
    buckets: dict[str, list[float]] = {}
    for check in checks:
        if check.outcome == "skipped":
            continue
        buckets.setdefault(check.dimension, []).append(check.score)
    return {
        dimension: round(sum(values) / len(values), 3)
        for dimension, values in buckets.items()
        if values
    }


def overall_score(checks: Iterable[EvaluationCheck]) -> float:
    """Weighted mean across dimensions, using the configured dimension weights."""
    scores = dimension_scores(checks)
    if not scores:
        return 0.0
    weighted = sum(score * DIMENSION_WEIGHTS.get(dimension, 1.0) for dimension, score in scores.items())
    total_weight = sum(DIMENSION_WEIGHTS.get(dimension, 1.0) for dimension in scores)
    return round(weighted / total_weight, 3) if total_weight else 0.0


def failures(checks: Iterable[EvaluationCheck]) -> list[str]:
    return [
        f"{check.name}: {check.reason}"
        for check in checks
        if check.outcome == "fail" and check.reason
    ]


def warnings(checks: Iterable[EvaluationCheck]) -> list[str]:
    return [
        f"{check.name}: {check.reason}"
        for check in checks
        if check.outcome == "warn" and check.reason
    ]


def blocking_failures(checks: Iterable[EvaluationCheck]) -> list[str]:
    """Failures that should stop a journey from being shown at all."""
    blocking = {"safety", "schema_validity"}
    return [
        f"{check.name}: {check.reason}"
        for check in checks
        if check.outcome == "fail" and check.dimension in blocking
    ]
