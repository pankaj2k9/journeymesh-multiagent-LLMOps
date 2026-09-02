"""Deterministic evaluation rules.

Each rule inspects the finished state and returns one check. Nothing here
calls a model: dates, arithmetic, schemas, provenance labels and language are
all decidable, and decidable things should not be judged by an LLM.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

from app.core.constants import DATA_SOURCES, SUPPORTED_LANGUAGES
from app.evaluation.schemas import EvaluationCheck
from app.graph.state import AGENT_STATE_KEYS, TravelState

Rule = Callable[[TravelState], EvaluationCheck]

# Script ranges used for the language check.
_BENGALI = re.compile(r"[ঀ-৿]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


def _check(
    name: str,
    dimension: str,
    *,
    score: float,
    outcome: str,
    reason: str,
    evidence: dict[str, Any] | None = None,
    weight: float = 1.0,
) -> EvaluationCheck:
    return EvaluationCheck(
        name=name,
        dimension=dimension,
        kind="deterministic",
        outcome=outcome,  # type: ignore[arg-type]
        score=round(max(0.0, min(1.0, score)), 3),
        weight=weight,
        reason=reason,
        evidence=evidence or {},
    )


# ---- schema validity -----------------------------------------------------
def schema_validity(state: TravelState) -> EvaluationCheck:
    """Every produced slice must validate against its Pydantic model."""
    from app.schemas.budget import BudgetAnalysis
    from app.schemas.flight import FlightResults
    from app.schemas.hotel import HotelResults
    from app.schemas.itinerary import ItineraryPlan
    from app.schemas.weather import WeatherInfo

    models = {
        "flight_results": FlightResults,
        "hotel_results": HotelResults,
        "weather_info": WeatherInfo,
        "budget_analysis": BudgetAnalysis,
        "itinerary_plan": ItineraryPlan,
    }
    failures: list[str] = []
    checked = 0
    for key, model in models.items():
        payload = state.get(key)
        if not payload:
            continue
        checked += 1
        try:
            model.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{key}: {type(exc).__name__}")

    if not checked:
        return _check(
            "schema_validity",
            "schema_validity",
            score=0.0,
            outcome="skipped",
            reason="No agent output was produced.",
        )
    score = 1.0 - len(failures) / checked
    return _check(
        "schema_validity",
        "schema_validity",
        score=score,
        outcome="pass" if not failures else "fail",
        reason="All agent outputs validate." if not failures else f"Invalid: {failures}",
        evidence={"checked": checked, "failures": failures},
    )


# ---- completeness --------------------------------------------------------
def completeness(state: TravelState) -> EvaluationCheck:
    """Every selected agent must have left something behind."""
    selected = list(state.get("selected_agents") or [])
    if not selected:
        return _check(
            "completeness",
            "completeness",
            score=0.0,
            outcome="skipped",
            reason="No agents were selected.",
        )
    missing = [
        agent
        for agent in selected
        if agent in AGENT_STATE_KEYS and not state.get(AGENT_STATE_KEYS[agent])
    ]
    score = 1.0 - len(missing) / len(selected)
    return _check(
        "completeness",
        "completeness",
        score=score,
        outcome="pass" if not missing else ("warn" if score >= 0.6 else "fail"),
        reason="Every selected agent produced output."
        if not missing
        else f"No output from: {', '.join(missing)}",
        evidence={"selected": selected, "missing": missing},
    )


# ---- relevance -----------------------------------------------------------
def relevance(state: TravelState) -> EvaluationCheck:
    """The answer must address the destination and the stated interests."""
    constraints = state.get("trip_constraints") or {}
    destination = (constraints.get("destination") or "").strip().lower()
    if not destination:
        return _check(
            "relevance",
            "relevance",
            score=0.5,
            outcome="warn",
            reason="No destination was given, so relevance cannot be measured precisely.",
        )

    hits = 0
    total = 0
    itinerary = state.get("itinerary_plan") or {}
    if itinerary:
        total += 1
        if destination in str(itinerary.get("destination", "")).lower():
            hits += 1
    hotels = state.get("hotel_results") or {}
    if hotels:
        total += 1
        if destination in str(hotels.get("destination", "")).lower():
            hits += 1
    weather = state.get("weather_info") or {}
    if weather:
        total += 1
        if destination in str(weather.get("location", "")).lower():
            hits += 1

    if not total:
        return _check(
            "relevance", "relevance", score=0.0, outcome="skipped", reason="Nothing to assess."
        )

    interests = set(constraints.get("interests") or [])
    tags = {
        tag
        for day in (itinerary.get("days") or [])
        for slot in day.get("slots", [])
        for activity in slot.get("activities", [])
        for tag in (activity.get("tags") or [])
    }
    interest_score = len(interests & tags) / len(interests) if interests else 1.0
    score = 0.6 * (hits / total) + 0.4 * interest_score
    return _check(
        "relevance",
        "relevance",
        score=score,
        outcome="pass" if score >= 0.7 else "warn",
        reason=f"{hits}/{total} sections reference the destination; "
        f"{len(interests & tags)}/{len(interests) or 0} interests covered.",
        evidence={"matched_interests": sorted(interests & tags)},
    )


# ---- groundedness --------------------------------------------------------
def groundedness(state: TravelState) -> EvaluationCheck:
    """Every price must carry a provenance label, and estimates must say so."""
    unlabeled: list[str] = []
    labeled = 0

    for option in (state.get("flight_results") or {}).get("options", []):
        if option.get("price_per_traveler") is None:
            continue
        source = option.get("price_source")
        labeled += 1
        if source not in DATA_SOURCES:
            unlabeled.append(f"flight:{option.get('airline')}")

    for option in (state.get("hotel_results") or {}).get("options", []):
        if option.get("price_per_night") is None:
            continue
        source = option.get("price_source")
        labeled += 1
        if source not in DATA_SOURCES:
            unlabeled.append(f"hotel:{option.get('name')}")

    budget = state.get("budget_analysis") or {}
    for line, record in (budget.get("line_provenance") or {}).items():
        labeled += 1
        if record.get("source") not in DATA_SOURCES:
            unlabeled.append(f"budget:{line}")

    if not labeled:
        return _check(
            "groundedness",
            "groundedness",
            score=0.5,
            outcome="warn",
            reason="No priced item was produced, so provenance could not be assessed.",
        )

    score = 1.0 - len(unlabeled) / labeled
    return _check(
        "groundedness",
        "groundedness",
        score=score,
        outcome="pass" if not unlabeled else "fail",
        reason="Every price carries a provenance label."
        if not unlabeled
        else f"Missing provenance: {unlabeled[:3]}",
        evidence={"labeled": labeled, "unlabeled": len(unlabeled)},
    )


# ---- consistency ---------------------------------------------------------
def date_consistency(state: TravelState) -> EvaluationCheck:
    constraints = state.get("trip_constraints") or {}
    departure = constraints.get("departure_date")
    returning = constraints.get("return_date")
    issues: list[str] = []

    start: date | None = None
    end: date | None = None
    if departure:
        try:
            start = date.fromisoformat(str(departure))
        except ValueError:
            issues.append("departure_date is not a valid date")
    if returning:
        try:
            end = date.fromisoformat(str(returning))
        except ValueError:
            issues.append("return_date is not a valid date")
    if start and end and end < start:
        issues.append("return date precedes departure date")

    days = (state.get("itinerary_plan") or {}).get("days") or []
    if start and days:
        for day in days:
            if not day.get("date"):
                continue
            try:
                day_date = date.fromisoformat(str(day["date"]))
            except ValueError:
                issues.append(f"day {day.get('day')} has an invalid date")
                continue
            if day_date < start:
                issues.append(f"day {day.get('day')} falls before departure")
                break
            if end and day_date > end:
                issues.append(f"day {day.get('day')} falls after the return date")
                break

    expected_days = constraints.get("trip_days")
    if expected_days and days and len(days) != int(expected_days):
        issues.append(f"itinerary has {len(days)} days for a {expected_days}-day trip")

    if not departure and not days:
        return _check(
            "date_consistency",
            "consistency",
            score=0.5,
            outcome="skipped",
            reason="No dates were supplied.",
        )
    score = 1.0 if not issues else max(0.0, 1.0 - 0.34 * len(issues))
    return _check(
        "date_consistency",
        "consistency",
        score=score,
        outcome="pass" if not issues else "fail",
        reason="Dates are internally consistent." if not issues else "; ".join(issues),
        evidence={"issues": issues},
    )


# ---- budget consistency --------------------------------------------------
def budget_arithmetic(state: TravelState) -> EvaluationCheck:
    budget = state.get("budget_analysis") or {}
    breakdown = budget.get("breakdown") or {}
    if not breakdown:
        return _check(
            "budget_arithmetic",
            "budget_consistency",
            score=0.0,
            outcome="skipped",
            reason="No budget analysis was produced.",
        )

    computed = round(
        sum(
            float(breakdown.get(key, 0) or 0)
            for key in ("flights", "hotels", "food", "transport", "activities", "miscellaneous")
        ),
        2,
    )
    stated = round(float(budget.get("estimated_total", 0) or 0), 2)
    issues: list[str] = []
    if abs(stated - computed) > 1.0:
        issues.append(f"estimated_total {stated} != breakdown {computed}")

    total_budget = budget.get("total_budget")
    remaining = budget.get("remaining_budget")
    if total_budget is not None and remaining is not None:
        expected = round(float(total_budget) - stated, 2)
        if abs(float(remaining) - expected) > 1.0:
            issues.append(f"remaining_budget {remaining} != {expected}")

    status = budget.get("budget_status")
    if total_budget:
        ratio = stated / float(total_budget)
        expected_status = (
            "over_budget" if ratio > 1.0 else ("near_limit" if ratio >= 0.92 else "within_budget")
        )
        if status != expected_status:
            issues.append(f"status '{status}' does not match a ratio of {ratio:.2f}")

    score = 1.0 if not issues else max(0.0, 1.0 - 0.4 * len(issues))
    return _check(
        "budget_arithmetic",
        "budget_consistency",
        score=score,
        outcome="pass" if not issues else "fail",
        reason="Budget arithmetic checks out." if not issues else "; ".join(issues),
        evidence={"computed": computed, "stated": stated, "issues": issues},
    )


# ---- itinerary feasibility ----------------------------------------------
def itinerary_feasibility(state: TravelState) -> EvaluationCheck:
    itinerary = state.get("itinerary_plan") or {}
    days = itinerary.get("days") or []
    if not days:
        return _check(
            "itinerary_feasibility",
            "itinerary_feasibility",
            score=0.0,
            outcome="skipped",
            reason="No itinerary was produced.",
        )

    issues: list[str] = []
    seen_titles: list[str] = []
    for day in days:
        slots = day.get("slots") or []
        if not slots:
            issues.append(f"day {day.get('day')} has no activities")
            continue
        minutes = 0
        for slot in slots:
            minutes += int(slot.get("travel_time_minutes") or 0)
            for activity in slot.get("activities", []):
                minutes += int(activity.get("duration_minutes") or 0)
                title = (activity.get("title") or "").strip().lower()
                if title:
                    seen_titles.append(title)
        if minutes > 14 * 60:
            issues.append(f"day {day.get('day')} schedules {minutes // 60}h of activity")

    duplicates = {title for title in seen_titles if seen_titles.count(title) > 2}
    if duplicates:
        issues.append(f"repeated activities: {', '.join(sorted(duplicates)[:2])}")

    score = 1.0 if not issues else max(0.0, 1.0 - 0.25 * len(issues))
    return _check(
        "itinerary_feasibility",
        "itinerary_feasibility",
        score=score,
        outcome="pass" if not issues else ("warn" if score >= 0.6 else "fail"),
        reason="Daily pacing is realistic." if not issues else "; ".join(issues),
        evidence={"days": len(days), "issues": issues},
    )


# ---- tool correctness ----------------------------------------------------
def tool_correctness(state: TravelState) -> EvaluationCheck:
    statuses = state.get("provider_status") or []
    if not statuses:
        return _check(
            "tool_correctness",
            "tool_correctness",
            score=0.5,
            outcome="skipped",
            reason="No provider calls were made.",
        )
    successful = sum(1 for status in statuses if status.get("ok"))
    score = successful / len(statuses)
    blocked = [
        result
        for result in (state.get("guardrail_results") or [])
        if result.get("stage") == "tool" and not result.get("allowed")
    ]
    return _check(
        "tool_correctness",
        "tool_correctness",
        score=score,
        outcome="pass" if score >= 0.8 else ("warn" if score >= 0.5 else "fail"),
        reason=f"{successful}/{len(statuses)} provider calls succeeded.",
        evidence={"blocked_calls": len(blocked)},
    )


# ---- safety --------------------------------------------------------------
def safety(state: TravelState) -> EvaluationCheck:
    results = state.get("guardrail_results") or []
    output_failures = [
        result
        for result in results
        if result.get("stage") == "output" and not result.get("allowed")
    ]
    redactions = [
        category
        for result in results
        for category in (result.get("redactions") or [])
    ]
    if output_failures:
        return _check(
            "safety",
            "safety",
            score=0.0,
            outcome="fail",
            reason="The output guard rejected this response.",
            evidence={"failures": output_failures[0].get("failures", [])},
        )
    score = 1.0 if not redactions else 0.85
    return _check(
        "safety",
        "safety",
        score=score,
        outcome="pass",
        reason="No unsafe content was detected."
        + (f" {len(redactions)} value(s) were redacted." if redactions else ""),
        evidence={"redaction_categories": sorted(set(redactions))},
    )


# ---- language correctness -----------------------------------------------
def language_correctness(state: TravelState) -> EvaluationCheck:
    constraints = state.get("trip_constraints") or {}
    language = constraints.get("response_language") or state.get("response_language") or "en"
    if language not in SUPPORTED_LANGUAGES:
        return _check(
            "language_correctness",
            "language_correctness",
            score=0.0,
            outcome="fail",
            reason=f"'{language}' is not a supported response language.",
        )

    final = state.get("final_response") or {}
    if not final:
        return _check(
            "language_correctness",
            "language_correctness",
            score=1.0,
            outcome="skipped",
            reason="The final response has not been generated yet.",
        )

    sample = " ".join(
        str(value)
        for value in (
            (final.get("overview") or {}).get("title"),
            (final.get("overview") or {}).get("headline"),
            final.get("closing_note"),
            *(final.get("travel_tips") or [])[:3],
        )
        if value
    )
    if language == "bn":
        ok = bool(_BENGALI.search(sample))
    elif language == "hi":
        ok = bool(_DEVANAGARI.search(sample))
    else:
        ok = bool(_LATIN_WORD.search(sample))

    return _check(
        "language_correctness",
        "language_correctness",
        score=1.0 if ok else 0.0,
        outcome="pass" if ok else "fail",
        reason=f"The final response is rendered in '{language}'."
        if ok
        else f"The final response is not in '{language}'.",
    )


DETERMINISTIC_RULES: tuple[Rule, ...] = (
    schema_validity,
    completeness,
    relevance,
    groundedness,
    date_consistency,
    budget_arithmetic,
    itinerary_feasibility,
    tool_correctness,
    safety,
    language_correctness,
)
