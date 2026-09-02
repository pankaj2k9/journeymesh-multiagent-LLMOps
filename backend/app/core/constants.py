"""Values that are shared across JourneyMesh and never change at runtime."""

from __future__ import annotations

APP_TAGLINE = "Every journey, intelligently connected."
API_PREFIX = "/api/v1"

# --- Language ------------------------------------------------------------
DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "bn", "hi")
LANGUAGE_LABELS = {
    "en": "English",
    "bn": "Bengali",
    "hi": "Hindi",
}

# --- Agents --------------------------------------------------------------
SUPERVISOR = "supervisor"
FLIGHT_AGENT = "flight_agent"
HOTEL_AGENT = "hotel_agent"
WEATHER_AGENT = "weather_agent"
BUDGET_AGENT = "budget_agent"
ITINERARY_AGENT = "itinerary_agent"
FINAL_RESPONSE_AGENT = "final_response_agent"

SPECIALIST_AGENTS = (
    FLIGHT_AGENT,
    HOTEL_AGENT,
    WEATHER_AGENT,
    BUDGET_AGENT,
    ITINERARY_AGENT,
)

# Execution order matters: budget consumes flight/hotel output, and the
# itinerary consumes everything before it.
AGENT_EXECUTION_ORDER = (
    FLIGHT_AGENT,
    HOTEL_AGENT,
    WEATHER_AGENT,
    BUDGET_AGENT,
    ITINERARY_AGENT,
)

# Downstream agents that must be refreshed when an upstream agent re-runs.
AGENT_DEPENDENTS = {
    FLIGHT_AGENT: (BUDGET_AGENT, ITINERARY_AGENT),
    HOTEL_AGENT: (BUDGET_AGENT, ITINERARY_AGENT),
    WEATHER_AGENT: (ITINERARY_AGENT,),
    BUDGET_AGENT: (ITINERARY_AGENT,),
    ITINERARY_AGENT: (),
}

# --- Data provenance -----------------------------------------------------
SOURCE_LIVE = "LIVE"
SOURCE_SEARCH_DERIVED = "SEARCH_DERIVED"
SOURCE_ESTIMATE = "ESTIMATE"
SOURCE_UNAVAILABLE = "UNAVAILABLE"
DATA_SOURCES = (SOURCE_LIVE, SOURCE_SEARCH_DERIVED, SOURCE_ESTIMATE, SOURCE_UNAVAILABLE)

# --- Review lifecycle ----------------------------------------------------
REVIEW_PENDING = "pending"
REVIEW_AWAITING = "awaiting_review"
REVIEW_APPROVED = "approved"
REVIEW_CHANGES_REQUESTED = "changes_requested"
REVIEW_REVISING = "revision_in_progress"
REVIEW_LIMIT_REACHED = "revision_limit_reached"

TRIP_DRAFT = "draft"
TRIP_AWAITING_REVIEW = "awaiting_review"
TRIP_REVISING = "revision_in_progress"
TRIP_APPROVED = "approved"
TRIP_FAILED = "failed"
TRIP_REJECTED = "rejected"

# --- Budget --------------------------------------------------------------
BUDGET_WITHIN = "within_budget"
BUDGET_NEAR_LIMIT = "near_limit"
BUDGET_OVER = "over_budget"
BUDGET_INSUFFICIENT = "insufficient_data"
NEAR_LIMIT_THRESHOLD = 0.92

# --- Travel taxonomy -----------------------------------------------------
TRAVEL_STYLES = (
    "budget",
    "comfort",
    "luxury",
    "adventure",
    "family",
    "business",
    "relaxed",
)

INTERESTS = (
    "food",
    "nature",
    "history",
    "culture",
    "shopping",
    "beaches",
    "nightlife",
    "photography",
    "technology",
    "family_activities",
)

HOTEL_PREFERENCES = (
    "any",
    "hostel",
    "guesthouse",
    "three_star",
    "four_star",
    "five_star",
    "apartment",
    "resort",
)

SUPPORTED_CURRENCIES = ("USD", "EUR", "GBP", "INR", "BDT", "AED", "SGD", "JPY", "AUD")

# --- Audit events --------------------------------------------------------
EVENT_PROMPT_INJECTION_BLOCKED = "PROMPT_INJECTION_BLOCKED"
EVENT_TOOL_CALL_BLOCKED = "TOOL_CALL_BLOCKED"
EVENT_INVALID_REQUEST = "INVALID_REQUEST"
EVENT_RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
EVENT_OUTPUT_VALIDATION_FAILED = "OUTPUT_VALIDATION_FAILED"
EVENT_PROVIDER_FAILURE = "PROVIDER_FAILURE"
EVENT_PII_REDACTED = "PII_REDACTED"
EVENT_HUMAN_REVIEW_APPROVED = "HUMAN_REVIEW_APPROVED"
EVENT_HUMAN_REVIEW_CHANGES_REQUESTED = "HUMAN_REVIEW_CHANGES_REQUESTED"
EVENT_REVISION_LIMIT_REACHED = "REVISION_LIMIT_REACHED"
EVENT_TRIP_PLANNED = "TRIP_PLANNED"
EVENT_TRIP_DELETED = "TRIP_DELETED"

REDACTION_TOKEN = "[REDACTED]"
