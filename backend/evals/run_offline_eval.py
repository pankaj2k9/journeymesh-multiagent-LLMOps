"""Run the JourneyMesh offline evaluation suite.

    cd backend
    python -m evals.run_offline_eval           # run every case
    python -m evals.run_offline_eval --case weather_only

The suite exercises the real graph with providers in their offline mode, so
it needs no API key and is safe to run in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation.runner import (  # noqa: E402
    load_cases,
    render_report,
    run_suite,
    write_report,
)
from app.observability.logging import configure_logging  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "cases.json"


async def main_async(selected: list[str] | None, quiet: bool) -> int:
    configure_logging(level="ERROR" if quiet else "INFO", fmt="text")
    cases = load_cases(CASES_PATH)
    if selected:
        cases = [case for case in cases if case.id in selected]
        if not cases:
            print(f"No case matched {selected}")
            return 2

    report = await run_suite(cases)
    print(render_report(report))
    path = write_report(report)
    print(f"\nreport written to {path}")
    return 0 if report.failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="JourneyMesh offline evaluation")
    parser.add_argument("--case", action="append", dest="cases", help="run one case by id")
    parser.add_argument("--verbose", action="store_true", help="show agent logs")
    args = parser.parse_args()
    return asyncio.run(main_async(args.cases, quiet=not args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
