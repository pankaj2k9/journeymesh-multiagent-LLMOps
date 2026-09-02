"""Evaluation schemas and the dimension catalogue."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import JourneyMeshModel
from app.schemas.evaluation import (  # re-exported for convenience
    CheckKind,
    CheckOutcome,
    EvaluationCheck,
    EvaluationResult,
)

__all__ = [
    "CheckKind",
    "CheckOutcome",
    "EvaluationCheck",
    "EvaluationResult",
    "DIMENSIONS",
    "DIMENSION_WEIGHTS",
    "EvalCase",
    "EvalCaseResult",
    "EvalReport",
]

# The ten dimensions JourneyMesh measures. Everything that can be checked
# deterministically is checked deterministically.
DIMENSIONS = (
    "relevance",
    "completeness",
    "groundedness",
    "consistency",
    "tool_correctness",
    "schema_validity",
    "safety",
    "language_correctness",
    "itinerary_feasibility",
    "budget_consistency",
)

DIMENSION_WEIGHTS: dict[str, float] = {
    "relevance": 1.0,
    "completeness": 1.2,
    "groundedness": 1.5,
    "consistency": 1.2,
    "tool_correctness": 0.8,
    "schema_validity": 1.5,
    "safety": 2.0,
    "language_correctness": 0.8,
    "itinerary_feasibility": 1.2,
    "budget_consistency": 1.3,
}


class EvalCase(JourneyMeshModel):
    """One offline evaluation case."""

    id: str
    description: str = ""
    request: dict[str, Any] = Field(default_factory=dict)
    expected_agents: list[str] = Field(default_factory=list)
    forbidden_agents: list[str] = Field(default_factory=list)
    expect_blocked: bool = False
    expect_language: str | None = None
    min_score: float = 0.7
    requested_changes: str | None = None
    expected_revision_agents: list[str] = Field(default_factory=list)
    preserved_agents: list[str] = Field(default_factory=list)


class EvalCaseResult(JourneyMeshModel):
    case_id: str
    passed: bool = False
    score: float = 0.0
    selected_agents: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    evaluation: EvaluationResult | None = None


class EvalReport(JourneyMeshModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    average_score: float = 0.0
    results: list[EvalCaseResult] = Field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return round(self.passed / self.total, 3) if self.total else 0.0
