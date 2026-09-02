"""The offline evaluation suite runs green."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.runner import load_cases, render_report, run_suite

CASES = Path(__file__).resolve().parents[1] / "evals" / "cases.json"


def test_the_case_file_is_valid():
    cases = load_cases(CASES)
    assert len(cases) >= 6
    ids = [case.id for case in cases]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_every_offline_case_passes():
    cases = load_cases(CASES)
    report = await run_suite(cases)
    assert report.failed == 0, render_report(report)
    assert report.average_score >= 0.7


@pytest.mark.asyncio
async def test_the_selective_re_execution_case_is_covered():
    cases = [case for case in load_cases(CASES) if case.id == "cheaper_hotel_revision"]
    assert cases, "the selective re-execution regression case is missing"
    report = await run_suite(cases)
    assert report.passed == 1, render_report(report)
