"""Output guardrails.

Runs after JSON parsing and Pydantic validation, immediately before the
result is evaluated and shown to a human. It answers: is this response
structurally complete, internally consistent, free of secrets, free of
unsafe markup and free of personal data we never asked for?
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from app.core.config import get_settings
from app.guardrails import pii_guard
from app.observability.logging import get_logger
from app.observability.tracing import current_context

logger = get_logger("journeymesh.output_guard")

_SECRET_PATTERNS = (
    re.compile(r"\b(gsk|sk|tvly)[-_][A-Za-z0-9]{16,}\b"),
    re.compile(r"\bpostgres(?:ql)?://[^\s\"']+", re.IGNORECASE),
    re.compile(r"\b(GROQ|TAVILY|AVIATIONSTACK|OPENWEATHER)_API_KEY\b"),
    re.compile(r"\bDATABASE_URL\s*=", re.IGNORECASE),
)

_UNSAFE_MARKUP = re.compile(
    r"(<\s*script|<\s*iframe|javascript:|on(?:error|load|click)\s*=|data:text/html)",
    re.IGNORECASE,
)

_UNSAFE_URL = re.compile(r"\b(?:ftp|file|data)://", re.IGNORECASE)

_ALLOWED_URL_SCHEMES = ("https://", "http://")

_CHAIN_OF_THOUGHT_MARKERS = (
    "chain of thought",
    "my reasoning is",
    "internal reasoning",
    "<thinking>",
    "as an ai language model",
)


@dataclass
class OutputDecision:
    allowed: bool = True
    reason_code: Optional[str] = None
    message: Optional[str] = None
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    sanitized: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": "output",
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "message": self.message,
            "failures": self.failures,
            "warnings": self.warnings,
            "redactions": self.redactions,
        }


def _walk_strings(value: Any, depth: int = 0):
    if depth > 10:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_strings(item, depth + 1)


def check_payload(payload: dict[str, Any], *, constraints: Any = None) -> OutputDecision:
    """Validate an assembled travel payload before it reaches a human."""
    settings = get_settings()
    decision = OutputDecision(sanitized=payload)

    if not settings.guardrails_enabled:
        return decision

    strings = list(_walk_strings(payload))
    blob = "\n".join(strings)

    # ---- secret leakage --------------------------------------------------
    for pattern in _SECRET_PATTERNS:
        if pattern.search(blob):
            decision.failures.append("possible credential or connection string in output")
            break

    # ---- unsafe markup ---------------------------------------------------
    if _UNSAFE_MARKUP.search(blob):
        decision.failures.append("unsafe markup in output")

    # ---- unsafe URLs -----------------------------------------------------
    if _UNSAFE_URL.search(blob):
        decision.failures.append("unsafe URL scheme in output")
    for candidate in re.findall(r"\b\w+://[^\s\"'<>]+", blob):
        if not candidate.lower().startswith(_ALLOWED_URL_SCHEMES):
            decision.failures.append(f"disallowed URL scheme: {candidate.split('://')[0]}")
            break

    # ---- leaked reasoning ------------------------------------------------
    lowered = blob.lower()
    for marker in _CHAIN_OF_THOUGHT_MARKERS:
        if marker in lowered:
            decision.warnings.append("model meta-commentary detected and should not be surfaced")
            break

    # ---- structural completeness ----------------------------------------
    decision.failures.extend(_check_required_sections(payload))

    # ---- internal consistency -------------------------------------------
    decision.warnings.extend(_check_consistency(payload, constraints))

    # ---- PII -------------------------------------------------------------
    if settings.pii_guard_enabled:
        sanitized, categories = pii_guard.sanitize_payload(payload)
        decision.sanitized = sanitized
        decision.redactions = categories
        if categories:
            logger.info(
                "PII_REDACTED", extra={"stage": "output", "categories": categories, **current_context()}
            )

    if decision.failures:
        decision.allowed = False
        decision.reason_code = "output_validation_failed"
        decision.message = "JourneyMesh could not verify the generated journey and stopped it."
        logger.warning(
            "OUTPUT_VALIDATION_FAILED",
            extra={"failures": decision.failures, **current_context()},
        )
    return decision


def _check_required_sections(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    selected = set(payload.get("selected_agents") or [])

    if "itinerary_agent" in selected:
        itinerary = payload.get("itinerary") or {}
        days = itinerary.get("days") or []
        if not days:
            failures.append("itinerary agent ran but produced no days")
        else:
            for day in days:
                if not day.get("slots"):
                    failures.append(f"day {day.get('day')} has no scheduled slots")
                    break

    if "budget_agent" in selected:
        budget = payload.get("budget") or {}
        if not budget.get("breakdown"):
            failures.append("budget agent ran but produced no breakdown")

    if "weather_agent" in selected:
        weather = payload.get("weather") or {}
        if not weather.get("forecast") and not weather.get("current"):
            failures.append("weather agent ran but returned no weather data")

    return failures


def _check_consistency(payload: dict[str, Any], constraints: Any) -> list[str]:
    warnings: list[str] = []
    budget = payload.get("budget") or {}
    breakdown = budget.get("breakdown") or {}

    if breakdown:
        computed = round(
            sum(
                float(breakdown.get(key, 0) or 0)
                for key in ("flights", "hotels", "food", "transport", "activities", "miscellaneous")
            ),
            2,
        )
        stated = round(float(budget.get("estimated_total", 0) or 0), 2)
        if stated and abs(stated - computed) > 1.0:
            warnings.append(
                f"budget total {stated} does not match its breakdown {computed}"
            )

    itinerary = payload.get("itinerary") or {}
    days = itinerary.get("days") or []
    if constraints is not None:
        expected = getattr(constraints, "trip_days", None)
        if expected and days and len(days) != expected:
            warnings.append(f"itinerary covers {len(days)} days but the trip is {expected} days")

        departure = getattr(constraints, "departure_date", None)
        returning = getattr(constraints, "return_date", None)
        if isinstance(departure, date) and isinstance(returning, date) and returning < departure:
            warnings.append("return date precedes departure date")

    titles: list[str] = []
    for day in days:
        for slot in day.get("slots", []):
            for activity in slot.get("activities", []):
                title = (activity.get("title") or "").strip().lower()
                if title:
                    titles.append(title)
    duplicates = {title for title in titles if titles.count(title) > 2}
    if duplicates:
        warnings.append(f"repeated activities: {', '.join(sorted(duplicates)[:3])}")

    return warnings
