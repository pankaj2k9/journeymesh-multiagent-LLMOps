"""Evaluation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import JourneyMeshModel, utcnow

CheckKind = Literal["deterministic", "llm_judge"]
CheckOutcome = Literal["pass", "warn", "fail", "skipped"]


class EvaluationCheck(JourneyMeshModel):
    name: str
    dimension: str
    kind: CheckKind = "deterministic"
    outcome: CheckOutcome = "skipped"
    score: float = 0.0
    weight: float = 1.0
    reason: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(JourneyMeshModel):
    overall_score: float = 0.0
    passed: bool = False
    mode: str = "deterministic"
    checks: list[EvaluationCheck] = Field(default_factory=list)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utcnow)

    def summary(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "passed": self.passed,
            "mode": self.mode,
            "dimension_scores": self.dimension_scores,
            "failure_count": len(self.failures),
            "warning_count": len(self.warnings),
        }


class GuardrailDecision(JourneyMeshModel):
    stage: Literal["input", "output", "tool"]
    allowed: bool = True
    reasons: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utcnow)
