"""Input guardrails.

Structural validation is handled by Pydantic on the request models. This
module adds the semantic layer: relevance, sanity of the travel constraints,
prompt-injection screening and PII redaction, and it produces a single
auditable decision object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.constants import SUPPORTED_LANGUAGES
from app.guardrails import pii_guard, prompt_injection, unlawful_intent
from app.observability.logging import get_logger
from app.observability.tracing import current_context

logger = get_logger("journeymesh.input_guard")

MAX_QUERY_LENGTH = 4000
MAX_TRAVELERS = 20
MAX_TRIP_DAYS = 60
MAX_PAST_DAYS = 1
MAX_FUTURE_DAYS = 730

# Signals that the request is a travel-planning request at all.
_TRAVEL_HINTS = (
    "trip", "travel", "flight", "flights", "fly", "hotel", "hotels", "stay",
    "itinerary", "visit", "tour", "holiday", "vacation", "weather", "budget",
    "journey", "destination", "sightseeing", "airport", "booking", "beach",
    "resort", "backpack", "explore", "plan", "days in", "weekend",
)

_UNSAFE_MARKUP = ("<script", "javascript:", "onerror=", "onload=", "<iframe", "data:text/html")


@dataclass
class InputDecision:
    allowed: bool = True
    reason_code: str | None = None
    message: str | None = None
    guidance: str | None = None
    warnings: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    sanitized_query: str = ""
    injection_score: float = 0.0
    matched_rules: list[str] = field(default_factory=list)
    unlawful_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": "input",
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "message": self.message,
            "warnings": self.warnings,
            "redactions": self.redactions,
            "injection_score": self.injection_score,
            "matched_rules": self.matched_rules,
            "unlawful_rules": self.unlawful_rules,
        }


def _looks_like_travel_request(text: str, has_structured_fields: bool) -> bool:
    if has_structured_fields:
        return True
    lowered = text.lower()
    return any(hint in lowered for hint in _TRAVEL_HINTS)


def check_request(payload: Any) -> InputDecision:
    """Run every input guardrail against a validated ``TripPlanRequest``."""
    settings = get_settings()
    decision = InputDecision()

    raw_query = (getattr(payload, "query", "") or "").strip()
    decision.sanitized_query = raw_query

    if not settings.guardrails_enabled:
        decision.warnings.append("guardrails disabled by configuration")
        return decision

    # ---- size ------------------------------------------------------------
    if len(raw_query) > MAX_QUERY_LENGTH:
        return _block(
            decision,
            "payload_too_large",
            "The trip description is longer than JourneyMesh accepts.",
            "Please shorten the description to under 4000 characters.",
        )

    # ---- markup / script injection --------------------------------------
    lowered = raw_query.lower()
    if any(marker in lowered for marker in _UNSAFE_MARKUP):
        return _block(
            decision,
            "unsafe_markup",
            "The request contained markup that JourneyMesh will not process.",
            "Please describe your trip in plain text.",
        )

    # ---- unlawful intent -------------------------------------------------
    # Runs before the injection classifier and before anything expensive: a
    # request to commit a crime is refused outright, so no agent is selected,
    # no tool is authorised and no provider is contacted.
    combined_text = " \n".join(
        part
        for part in (
            raw_query,
            getattr(payload, "additional_instructions", None),
            getattr(payload, "special_requirements", None),
        )
        if part
    )
    unlawful = unlawful_intent.scan(combined_text)
    if unlawful.blocked:
        decision.unlawful_rules = unlawful.matched_rules
        logger.warning(
            "UNLAWFUL_REQUEST_BLOCKED",
            extra={"rules": unlawful.matched_rules, **current_context()},
        )
        return _block(
            decision,
            "unlawful_request",
            unlawful.reason or "This request asks for something unlawful.",
            "Ask for the trip itself - for example, 'Plan 5 days in Dubai with "
            "flights, hotels and sightseeing'.",
        )

    # ---- prompt injection ------------------------------------------------
    if settings.prompt_injection_check_enabled:
        combined = " \n".join(
            part
            for part in (
                raw_query,
                getattr(payload, "additional_instructions", None),
                getattr(payload, "special_requirements", None),
            )
            if part
        )
        verdict = prompt_injection.scan(combined)
        decision.injection_score = verdict.score
        decision.matched_rules = verdict.matched_rules
        if verdict.blocked:
            logger.warning(
                "PROMPT_INJECTION_BLOCKED",
                extra={"rules": verdict.matched_rules, "score": verdict.score, **current_context()},
            )
            return _block(
                decision,
                "prompt_injection_blocked",
                verdict.reason or "The request was blocked by JourneyMesh safety checks.",
                "Ask a travel question instead - for example, 'Plan 4 days in Kyoto under $1,500'.",
            )
        if verdict.suspicious:
            decision.warnings.append(f"suspicious phrasing: {', '.join(verdict.matched_rules)}")

    # ---- relevance -------------------------------------------------------
    has_structured = bool(getattr(payload, "destination", None) or getattr(payload, "origin", None))
    if not _looks_like_travel_request(raw_query, has_structured):
        return _block(
            decision,
            "off_topic",
            "JourneyMesh only answers travel planning questions.",
            "Try describing a destination, dates and a budget.",
        )

    # ---- semantic constraint checks -------------------------------------
    error = _check_constraints(payload)
    if error:
        return _block(decision, "invalid_constraints", error, "Adjust the trip details and retry.")

    # ---- language --------------------------------------------------------
    language = getattr(payload, "response_language", "en")
    if language not in SUPPORTED_LANGUAGES:
        return _block(
            decision,
            "unsupported_language",
            f"Supported response languages are: {', '.join(SUPPORTED_LANGUAGES)}.",
            "Choose English, Bengali or Hindi.",
        )

    # ---- PII -------------------------------------------------------------
    if settings.pii_guard_enabled:
        result = pii_guard.redact_text(raw_query)
        decision.sanitized_query = result.text
        decision.redactions = result.categories
        if result.categories:
            logger.info("PII_REDACTED", extra={"categories": result.categories, **current_context()})
            decision.warnings.append(
                "Personal document details were removed from the request before processing."
            )
        if pii_guard.mentions_travel_documents(raw_query):
            decision.warnings.append(
                "JourneyMesh does not need passport, visa or payment details to plan a journey."
            )

    return decision


def _check_constraints(payload: Any) -> str | None:
    departure: date | None = getattr(payload, "departure_date", None)
    returning: date | None = getattr(payload, "return_date", None)
    travelers = getattr(payload, "travelers", 1) or 1
    budget = getattr(payload, "budget", None)

    if travelers < 1:
        return "At least one traveller is required."
    if travelers > MAX_TRAVELERS:
        return f"JourneyMesh plans for up to {MAX_TRAVELERS} travellers per journey."
    if budget is not None and budget < 0:
        return "Budget cannot be negative."
    if budget is not None and travelers and budget > 0 and budget / travelers < 1:
        return "The budget is too small to plan a journey with."

    today = date.today()
    if departure and departure < today - timedelta(days=MAX_PAST_DAYS):
        return "Departure date is in the past."
    if departure and departure > today + timedelta(days=MAX_FUTURE_DAYS):
        return "Departure date is too far in the future to plan reliably."
    if departure and returning:
        if returning < departure:
            return "Return date must not be earlier than the departure date."
        if (returning - departure).days > MAX_TRIP_DAYS:
            return f"JourneyMesh plans journeys of up to {MAX_TRIP_DAYS} days."
    return None


def check_change_request(text: str) -> InputDecision:
    """Guardrails for the free-text 'request changes' field."""
    settings = get_settings()
    decision = InputDecision(sanitized_query=(text or "").strip())

    if not settings.guardrails_enabled:
        return decision

    if len(decision.sanitized_query) < 3:
        return _block(
            decision,
            "invalid_constraints",
            "Tell JourneyMesh what you would like to change.",
            "For example: 'Find a cheaper hotel under $120 per night.'",
        )
    if len(decision.sanitized_query) > 2000:
        return _block(
            decision,
            "payload_too_large",
            "The change request is too long.",
            "Please keep the change request under 2000 characters.",
        )
    if any(marker in decision.sanitized_query.lower() for marker in _UNSAFE_MARKUP):
        return _block(
            decision,
            "unsafe_markup",
            "The change request contained markup that JourneyMesh will not process.",
            "Please describe the change in plain text.",
        )

    if settings.prompt_injection_check_enabled:
        verdict = prompt_injection.scan(decision.sanitized_query)
        decision.injection_score = verdict.score
        decision.matched_rules = verdict.matched_rules
        if verdict.blocked:
            logger.warning(
                "PROMPT_INJECTION_BLOCKED",
                extra={"stage": "change_request", "rules": verdict.matched_rules, **current_context()},
            )
            return _block(
                decision,
                "prompt_injection_blocked",
                verdict.reason or "The change request was blocked by JourneyMesh safety checks.",
                "Describe the change you want to your journey instead.",
            )

    if settings.pii_guard_enabled:
        result = pii_guard.redact_text(decision.sanitized_query)
        decision.sanitized_query = result.text
        decision.redactions = result.categories

    return decision


def _block(
    decision: InputDecision, code: str, message: str, guidance: str | None = None
) -> InputDecision:
    decision.allowed = False
    decision.reason_code = code
    decision.message = message
    decision.guidance = guidance
    return decision
