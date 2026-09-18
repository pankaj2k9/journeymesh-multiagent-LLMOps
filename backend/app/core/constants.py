"""Values that are shared across Travel Crew AI and never change at runtime."""

from __future__ import annotations

APP_TAGLINE = "Your AI crew for every journey."
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
SOURCE_CACHED = "CACHED"
SOURCE_SEARCH_DERIVED = "SEARCH_DERIVED"
SOURCE_ESTIMATE = "ESTIMATE"
SOURCE_MOCK = "MOCK"
SOURCE_UNAVAILABLE = "UNAVAILABLE"
DATA_SOURCES = (
    SOURCE_LIVE,
    SOURCE_CACHED,
    SOURCE_SEARCH_DERIVED,
    SOURCE_ESTIMATE,
    SOURCE_MOCK,
    SOURCE_UNAVAILABLE,
)

# Sources whose money a traveller may be asked to commit to. Anything outside
# this set is planning information and must never be presented as a payable
# amount, however confident it looks.
PAYABLE_SOURCES = (SOURCE_LIVE, SOURCE_CACHED)

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

# --- Identity and access -------------------------------------------------
ROLE_USER = "USER"
ROLE_SUPPORT = "SUPPORT"
ROLE_ADMIN = "ADMIN"
ROLES = (ROLE_USER, ROLE_SUPPORT, ROLE_ADMIN)

# Ordered weakest to strongest; `role_satisfies` compares by index.
ROLE_RANK = {ROLE_USER: 0, ROLE_SUPPORT: 1, ROLE_ADMIN: 2}

USER_ACTIVE = "active"
USER_SUSPENDED = "suspended"
USER_STATUSES = (USER_ACTIVE, USER_SUSPENDED)

TRAVELER_ADULT = "ADULT"
TRAVELER_CHILD = "CHILD"
TRAVELER_INFANT = "INFANT"
TRAVELER_TYPES = (TRAVELER_ADULT, TRAVELER_CHILD, TRAVELER_INFANT)

# A child stops being a child, for fare purposes, at 12.
CHILD_MAX_AGE = 11
INFANT_MAX_AGE = 1

# --- Trip preferences ----------------------------------------------------
CABIN_ECONOMY = "economy"
CABIN_PREMIUM_ECONOMY = "premium_economy"
CABIN_BUSINESS = "business"
CABIN_FIRST = "first"
CABIN_CLASSES = (CABIN_ECONOMY, CABIN_PREMIUM_ECONOMY, CABIN_BUSINESS, CABIN_FIRST)

PACE_RELAXED = "relaxed"
PACE_BALANCED = "balanced"
PACE_PACKED = "packed"
TRAVEL_PACES = (PACE_RELAXED, PACE_BALANCED, PACE_PACKED)

ACCOMMODATION_TYPES = (
    "any",
    "hotel",
    "hostel",
    "guesthouse",
    "apartment",
    "resort",
    "boutique",
)

BAGGAGE_NONE = "none"
BAGGAGE_CABIN = "cabin_only"
BAGGAGE_CHECKED = "checked"
BAGGAGE_OPTIONS = (BAGGAGE_NONE, BAGGAGE_CABIN, BAGGAGE_CHECKED)

# A flexible search may shift each date by at most this many days. Wider than
# a week turns one search into hundreds of provider calls.
MAX_FLEXIBLE_DAYS = 7
MAX_STOPS_CEILING = 3
MAX_CHILDREN = 9
MAX_ADULTS = 9
MAX_PREFERRED_AIRLINES = 10

# --- Budget ledger -------------------------------------------------------
CATEGORY_FLIGHT = "FLIGHT"
CATEGORY_ACCOMMODATION = "ACCOMMODATION"
CATEGORY_ACTIVITY = "ACTIVITY"
CATEGORY_LOCAL_TRANSPORT = "LOCAL_TRANSPORT"
CATEGORY_FOOD = "FOOD"
CATEGORY_MISCELLANEOUS = "MISCELLANEOUS"
BUDGET_CATEGORIES = (
    CATEGORY_FLIGHT,
    CATEGORY_ACCOMMODATION,
    CATEGORY_ACTIVITY,
    CATEGORY_LOCAL_TRANSPORT,
    CATEGORY_FOOD,
    CATEGORY_MISCELLANEOUS,
)

# The four ways money can be attached to a trip, weakest commitment first.
# An LLM may propose an ESTIMATE; only a deterministic service may write the
# other three, and only BOOKED/PAID may come from a provider confirmation.
ITEM_ESTIMATED = "ESTIMATED"
ITEM_SELECTED = "SELECTED"
ITEM_BOOKED = "BOOKED"
ITEM_PAID = "PAID"
BUDGET_ITEM_STATES = (ITEM_ESTIMATED, ITEM_SELECTED, ITEM_BOOKED, ITEM_PAID)

# committed = money the traveller is on the hook for; planned = chosen but not
# yet bought; estimated = the engine's own allowance for what is not chosen.
COMMITTED_STATES = (ITEM_BOOKED, ITEM_PAID)
PLANNED_STATES = (ITEM_SELECTED,)
ESTIMATED_STATES = (ITEM_ESTIMATED,)

# Legal transitions for a budget item. Money never moves backwards without a
# reversal row, so there is no PAID -> SELECTED edge.
BUDGET_ITEM_TRANSITIONS: dict[str, tuple[str, ...]] = {
    ITEM_ESTIMATED: (ITEM_SELECTED,),
    ITEM_SELECTED: (ITEM_BOOKED,),
    ITEM_BOOKED: (ITEM_PAID,),
    ITEM_PAID: (),
}

# Share of the total budget held back by default when a trip asks for a
# reserve without naming an amount.
DEFAULT_RESERVE_RATIO = "0.05"

# --- Audit events --------------------------------------------------------
EVENT_PROMPT_INJECTION_BLOCKED = "PROMPT_INJECTION_BLOCKED"
EVENT_UNLAWFUL_REQUEST_BLOCKED = "UNLAWFUL_REQUEST_BLOCKED"
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
EVENT_USER_REGISTERED = "USER_REGISTERED"
EVENT_USER_LOGIN = "USER_LOGIN"
EVENT_USER_LOGIN_FAILED = "USER_LOGIN_FAILED"
EVENT_SESSION_CLAIMED = "SESSION_CLAIMED"
EVENT_BUDGET_ITEM_ADDED = "BUDGET_ITEM_ADDED"
EVENT_BUDGET_ITEM_REVERSED = "BUDGET_ITEM_REVERSED"
EVENT_BUDGET_ITEM_PROMOTED = "BUDGET_ITEM_PROMOTED"
EVENT_BUDGET_RECOMPUTED = "BUDGET_RECOMPUTED"
EVENT_FORBIDDEN = "FORBIDDEN"

REDACTION_TOKEN = "[REDACTED]"
