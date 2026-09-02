"""The evaluation entry point.

``Evaluator.evaluate`` runs every deterministic rule, optionally adds the
LLM-as-judge checks, aggregates the result and decides whether the journey is
good enough to put in front of a human.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.evaluation import metrics, quality_checks
from app.evaluation.rules import DETERMINISTIC_RULES
from app.evaluation.schemas import EvaluationCheck, EvaluationResult
from app.graph.state import TravelState
from app.observability import metrics as telemetry
from app.observability.logging import get_logger
from app.observability.tracing import span
from app.services.llm_service import LLMService

logger = get_logger("journeymesh.evaluation")

MODES = ("deterministic", "hybrid", "llm_judge")


class Evaluator:
    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm

    async def evaluate(self, state: TravelState) -> EvaluationResult:
        settings = get_settings()
        mode = settings.evaluation_mode if settings.evaluation_mode in MODES else "deterministic"

        if not settings.evaluation_enabled:
            return EvaluationResult(
                mode="disabled",
                passed=True,
                overall_score=0.0,
                warnings=["Evaluation is disabled by configuration."],
            )

        checks: list[EvaluationCheck] = []
        with span("evaluation", kind="evaluation", mode=mode):
            if mode in ("deterministic", "hybrid"):
                for rule in DETERMINISTIC_RULES:
                    try:
                        checks.append(rule(state))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "evaluation rule failed",
                            extra={"rule": getattr(rule, "__name__", "?"), "error": str(exc)},
                        )
            if mode in ("hybrid", "llm_judge"):
                checks.extend(await quality_checks.judge(state, self.llm))

        result = EvaluationResult(
            mode=mode,
            checks=checks,
            dimension_scores=metrics.dimension_scores(checks),
            overall_score=metrics.overall_score(checks),
            failures=metrics.failures(checks),
            warnings=metrics.warnings(checks),
        )
        blocking = metrics.blocking_failures(checks)
        result.passed = (
            result.overall_score >= settings.evaluation_pass_threshold and not blocking
        )

        telemetry.increment("evaluation.runs", mode=mode, passed=str(result.passed))
        logger.info(
            "evaluation complete",
            extra={
                "overall_score": result.overall_score,
                "passed": result.passed,
                "failures": len(result.failures),
            },
        )
        return result


_evaluator: Evaluator | None = None


def get_evaluator() -> Evaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = Evaluator()
    return _evaluator
