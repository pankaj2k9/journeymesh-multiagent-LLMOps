"""Offline evaluation runner.

Runs a suite of evaluation cases through the real graph with providers in
their offline mode, so routing, guardrails, selective re-execution and output
quality can be regression-tested without any credential.

    python -m evals.run_offline_eval
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.evaluation.schemas import EvalCase, EvalCaseResult, EvalReport
from app.guardrails import input_guard
from app.observability.logging import get_logger
from app.schemas.travel import TripPlanRequest

logger = get_logger("journeymesh.evaluation.runner")


def load_cases(path: Path) -> list[EvalCase]:
    """Load evaluation cases from a JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    return [EvalCase.model_validate(case) for case in cases]


async def run_case(case: EvalCase) -> EvalCaseResult:
    """Execute one case end to end and score it."""
    from app.graph.travel_graph import get_workflow

    result = EvalCaseResult(case_id=case.id)

    try:
        request = TripPlanRequest.model_validate(case.request)
    except Exception as exc:  # noqa: BLE001
        if case.expect_blocked:
            result.passed = True
            result.score = 1.0
            return result
        result.failures.append(f"request did not validate: {exc}")
        return result

    decision = input_guard.check_request(request)
    if not decision.allowed:
        result.passed = case.expect_blocked
        result.score = 1.0 if case.expect_blocked else 0.0
        if not case.expect_blocked:
            result.failures.append(f"blocked by input guard: {decision.reason_code}")
        return result
    if case.expect_blocked:
        result.failures.append("expected the request to be blocked, but it passed")
        return result

    workflow = get_workflow()
    state = await workflow.plan(
        trip_id=f"eval-{case.id}",
        request=request,
        sanitized_query=decision.sanitized_query,
    )
    result.selected_agents = list(state.get("selected_agents") or [])

    missing = [agent for agent in case.expected_agents if agent not in result.selected_agents]
    unwanted = [agent for agent in case.forbidden_agents if agent in result.selected_agents]
    if missing:
        result.failures.append(f"missing agents: {missing}")
    if unwanted:
        result.failures.append(f"agents that should not have run: {unwanted}")

    if case.requested_changes:
        before = {
            key: state.get(key)
            for key in ("flight_results", "hotel_results", "weather_info")
        }
        state = await workflow.revise(state, requested_changes=case.requested_changes)
        rerun = list(state.get("selected_agents") or [])
        missing_rev = [a for a in case.expected_revision_agents if a not in rerun]
        if missing_rev:
            result.failures.append(f"revision did not re-run: {missing_rev}")
        for agent in case.preserved_agents:
            key = {
                "flight_agent": "flight_results",
                "hotel_agent": "hotel_results",
                "weather_agent": "weather_info",
            }.get(agent)
            if key and before.get(key) != state.get(key):
                result.failures.append(f"{agent} output was not preserved")

    evaluation = state.get("evaluation_results") or {}
    result.score = float(evaluation.get("overall_score") or 0.0)
    if case.expect_language:
        language = ((state.get("final_response") or {}).get("language")) or (
            state.get("trip_constraints") or {}
        ).get("response_language")
        if language != case.expect_language:
            result.failures.append(
                f"expected language '{case.expect_language}', produced '{language}'"
            )
    if result.score < case.min_score:
        result.failures.append(
            f"score {result.score:.2f} is below the required {case.min_score:.2f}"
        )

    result.passed = not result.failures
    return result


async def run_suite(cases: Iterable[EvalCase]) -> EvalReport:
    report = EvalReport()
    scores: list[float] = []
    for case in cases:
        outcome = await run_case(case)
        report.results.append(outcome)
        scores.append(outcome.score)
        report.total += 1
        if outcome.passed:
            report.passed += 1
        else:
            report.failed += 1
    report.average_score = round(sum(scores) / len(scores), 3) if scores else 0.0
    return report


def render_report(report: EvalReport) -> str:
    lines = [
        "JourneyMesh offline evaluation",
        "=" * 46,
        f"cases     : {report.total}",
        f"passed    : {report.passed}",
        f"failed    : {report.failed}",
        f"pass rate : {report.pass_rate:.0%}",
        f"avg score : {report.average_score:.3f}",
        "",
    ]
    for outcome in report.results:
        status = "PASS" if outcome.passed else "FAIL"
        lines.append(f"[{status}] {outcome.case_id} (score {outcome.score:.2f})")
        for failure in outcome.failures:
            lines.append(f"        - {failure}")
    return "\n".join(lines)


def write_report(report: EvalReport, directory: Path | None = None) -> Path:
    target = directory or Path(__file__).resolve().parents[2] / "evals" / "reports"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "latest.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def summarise(report: EvalReport) -> dict[str, Any]:
    return {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "pass_rate": report.pass_rate,
        "average_score": report.average_score,
    }
