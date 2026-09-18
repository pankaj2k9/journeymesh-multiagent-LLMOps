"""Turn a sentence into a flight search.

    "Find the cheapest flights from Dhaka to Rome for two adults and one child
     around June 10, flexible by three days, under $2,000 total, maximum one
     stop."

becomes a validated ``FlightSearchCriteria``. Deterministic patterns do the
work; the model is a fallback for the fields they miss, and its answer is
merged field by field rather than trusted wholesale.

The rule that shapes this module: **the model never supplies money.** A budget
ceiling is read from the traveller's own text by a regular expression, or it is
absent. A model asked to "extract the budget" will happily produce a plausible
one from a sentence that never mentioned a number, and a fabricated ceiling
silently filters real options out of a real search. Any amount the model
returns is discarded, and there is a test that proves it.

Prices themselves never come from here at all - only from a provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from app.agents.query_parser import (
    _WORD_NUMBERS,
    _budget_from_text,
    places_from_text,
)
from app.core.constants import (
    MAX_FLEXIBLE_DAYS,
    MAX_STOPS_CEILING,
)
from app.observability.logging import get_logger
from app.schemas.search import FlightSearchCriteria
from app.services.llm_service import get_llm_service

logger = get_logger("journeymesh.agents.search_parser")

# A child's age changes the fare, so the schema requires one. A sentence like
# "two adults and one child" does not carry it, and refusing to search would be
# a worse answer than searching with a stated assumption the traveller can see
# and correct before anything is booked. Mid-range on purpose: old enough not
# to be an infant, young enough to still attract a child fare.
ASSUMED_CHILD_AGE = 8


_NUM = r"(\d{1,2}|" + "|".join(_WORD_NUMBERS) + r")"


def _as_int(raw: str | None) -> int | None:
    if not raw:
        return None
    return _WORD_NUMBERS.get(raw.lower()) or (int(raw) if raw.isdigit() else None)


# ---- party --------------------------------------------------------------
_ADULTS = re.compile(rf"\b{_NUM}\s+adults?\b", re.IGNORECASE)
_CHILDREN = re.compile(rf"\b{_NUM}\s+(?:child(?:ren)?|kids?)\b", re.IGNORECASE)
_INFANTS = re.compile(rf"\b{_NUM}\s+(?:infants?|babies|baby)\b", re.IGNORECASE)
_CHILD_AGES = re.compile(
    r"\b(?:aged?|ages?)\s+((?:\d{1,2})(?:\s*(?:,|and|&)\s*\d{1,2})*)", re.IGNORECASE
)

# ---- stops --------------------------------------------------------------
_NON_STOP = re.compile(r"\b(non[-\s]?stop|direct(?:\s+only)?|no\s+(?:stops|layovers))\b", re.I)
_MAX_STOPS = re.compile(
    rf"\b(?:max(?:imum)?|at\s+most|no\s+more\s+than|up\s+to)\s+{_NUM}\s+stops?\b", re.I
)

# ---- flexibility --------------------------------------------------------
_FLEXIBLE = re.compile(
    rf"\bflexible\s+(?:by\s+|within\s+|\+/-\s*)?{_NUM}\s*days?\b"
    rf"|\b(?:\+/-|plus\s+or\s+minus)\s*{_NUM}\s*days?\b"
    rf"|\b{_NUM}\s*days?\s+(?:either\s+side|flexibility)\b",
    re.IGNORECASE,
)
_FLEXIBLE_VAGUE = re.compile(r"\b(flexible\s+dates?|dates?\s+are\s+flexible|around)\b", re.I)

# ---- cabin and bags -----------------------------------------------------
_CABIN = {
    "economy": re.compile(r"\beconomy\b", re.I),
    "premium_economy": re.compile(r"\bpremium\s+economy\b", re.I),
    "business": re.compile(r"\bbusiness\s+class\b", re.I),
    "first": re.compile(r"\bfirst\s+class\b", re.I),
}
_CHECKED_BAG = re.compile(
    r"\b(checked\s+bag|check(?:ed)?\s+luggage|hold\s+luggage|with\s+(?:a\s+)?bag)\b", re.I
)
_CABIN_ONLY = re.compile(r"\b(hand\s+luggage\s+only|carry[-\s]?on\s+only|cabin\s+bag\s+only)\b", re.I)

# ---- airlines -----------------------------------------------------------
_AVOID = re.compile(
    r"\b(?:avoid|not|no|exclude|except)\s+((?:[A-Z][\w'-]+\s?){1,3})", re.IGNORECASE
)
_PREFER = re.compile(r"\b(?:prefer|on|fly\s+with|with)\s+((?:[A-Z][\w'-]+\s?){1,3})")

_AIRLINE_NAMES = {
    "turkish airlines": "TK",
    "turkish": "TK",
    "emirates": "EK",
    "qatar airways": "QR",
    "qatar": "QR",
    "singapore airlines": "SQ",
    "etihad": "EY",
    "etihad airways": "EY",
    "biman": "BG",
    "biman bangladesh airlines": "BG",
    "indigo": "6E",
    "malaysia airlines": "MH",
    "ryanair": "FR",
}

# ---- time windows -------------------------------------------------------
_MORNING_DEPARTURE = re.compile(r"\bmorning\s+(?:departure|flight)\b", re.I)
_EVENING_DEPARTURE = re.compile(r"\bevening\s+(?:departure|flight)\b", re.I)
_ARRIVE_BEFORE = re.compile(rf"\barriv\w*\s+before\s+{_NUM}\s*(am|pm)?\b", re.I)
_DEPART_AFTER = re.compile(rf"\bdepart\w*\s+after\s+{_NUM}\s*(am|pm)?\b", re.I)

# ---- dates --------------------------------------------------------------
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_DAY = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE
)
_DAY_MONTH = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(_MONTHS) + r")\b", re.IGNORECASE
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NIGHTS = re.compile(rf"\b(?:for\s+)?{_NUM}\s+(?:nights?|days?)\b", re.IGNORECASE)
_RETURNING = re.compile(r"\b(return(?:ing)?|coming\s+back|back\s+on)\b", re.I)


@dataclass
class ParsedSearch:
    """What the parser understood, and what it could not.

    ``missing`` drives the interface: a search that cannot run yet asks for the
    two fields it needs rather than guessing them or failing with a 422.
    """

    criteria: FlightSearchCriteria | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    used_model: bool = False

    @property
    def complete(self) -> bool:
        return self.criteria is not None


def parse_deterministic(text: str, *, today: date | None = None) -> dict[str, Any]:
    """Everything the patterns can extract. No model, no network."""
    reference = today or date.today()
    fields: dict[str, Any] = {}

    origin, destination = places_from_text(text)
    if origin:
        fields["origin"] = origin
    if destination:
        fields["destination"] = destination

    # ---- party ----------------------------------------------------------
    adults = _as_int(_first_group(_ADULTS, text))
    children = _as_int(_first_group(_CHILDREN, text))
    if adults:
        fields["adults"] = adults
    if children:
        fields["children"] = children
        ages_match = _CHILD_AGES.search(text)
        ages: list[int] = []
        if ages_match:
            ages = [int(part) for part in re.findall(r"\d{1,2}", ages_match.group(1))]
        if len(ages) == children:
            fields["child_ages"] = ages
        else:
            fields["child_ages"] = [ASSUMED_CHILD_AGE] * children
            fields["_child_age_assumed"] = True
    if _INFANTS.search(text):
        # Infants are priced differently and are not modelled yet. Say so
        # rather than silently counting a lap infant as a seat.
        fields["_infants_mentioned"] = True

    # ---- dates ----------------------------------------------------------
    dates = _dates_from(text, reference)
    if dates:
        fields["departure_date"] = dates[0]
        if len(dates) > 1:
            fields["return_date"] = dates[1]
        elif _RETURNING.search(text):
            nights = _as_int(_first_group(_NIGHTS, text))
            if nights:
                fields["return_date"] = dates[0] + timedelta(days=nights)

    # ---- flexibility ----------------------------------------------------
    flexible = _as_int(_first_group(_FLEXIBLE, text))
    if flexible:
        fields["flexible_days"] = min(flexible, MAX_FLEXIBLE_DAYS)
    elif _FLEXIBLE_VAGUE.search(text):
        # "around June 10" is a real statement of flexibility; two days is the
        # smallest window that means anything, and it is reported as an
        # assumption rather than applied silently.
        fields["flexible_days"] = 2
        fields["_flexible_assumed"] = True

    # ---- stops ----------------------------------------------------------
    if _NON_STOP.search(text):
        fields["max_stops"] = 0
    else:
        stops = _as_int(_first_group(_MAX_STOPS, text))
        if stops is not None:
            fields["max_stops"] = min(stops, MAX_STOPS_CEILING)

    # ---- cabin ----------------------------------------------------------
    for cabin in ("first", "business", "premium_economy", "economy"):
        if _CABIN[cabin].search(text):
            fields["cabin_class"] = cabin
            break

    # ---- baggage --------------------------------------------------------
    if _CABIN_ONLY.search(text):
        fields["baggage"] = "cabin_only"
    elif _CHECKED_BAG.search(text):
        fields["baggage"] = "checked"

    # ---- airlines -------------------------------------------------------
    excluded = _airlines_in(text, _AVOID)
    preferred = [code for code in _airlines_in(text, _PREFER) if code not in excluded]
    if excluded:
        fields["excluded_airlines"] = excluded
    if preferred:
        fields["preferred_airlines"] = preferred

    # ---- time windows ---------------------------------------------------
    if _MORNING_DEPARTURE.search(text):
        fields["earliest_departure_hour"] = 5
        fields["latest_departure_hour"] = 11
    elif _EVENING_DEPARTURE.search(text):
        fields["earliest_departure_hour"] = 17
        fields["latest_departure_hour"] = 23

    arrive_before = _hour_from(_ARRIVE_BEFORE, text)
    if arrive_before is not None:
        fields["latest_arrival_hour"] = arrive_before
    depart_after = _hour_from(_DEPART_AFTER, text)
    if depart_after is not None:
        fields["earliest_departure_hour"] = depart_after

    # ---- money ----------------------------------------------------------
    # Read by a regular expression from the traveller's own words. Never by a
    # model, and never invented.
    amount, currency = _budget_from_text(text)
    if amount is not None:
        fields["max_total_price"] = amount
    if currency:
        fields["currency"] = currency

    return fields


async def parse(
    text: str,
    *,
    today: date | None = None,
    defaults: dict[str, Any] | None = None,
    allow_model: bool = True,
) -> ParsedSearch:
    """Parse a sentence into a search, using the model only to fill gaps."""
    fields = parse_deterministic(text, today=today)
    used_model = False

    needed = [key for key in ("origin", "destination", "departure_date") if key not in fields]
    if needed and allow_model:
        filled = await _model_fill(text, needed)
        # Filtered again here, at the point where model output joins trusted
        # fields. `_model_fill` already restricts its answer, but this is the
        # trust boundary: anything that widens or replaces that function - a
        # different model, a future adapter, a test double - still cannot put a
        # price, a currency or a routing constraint into a real search.
        filled = {
            key: value for key, value in (filled or {}).items() if key in _MODEL_MAY_SUPPLY
        }
        if filled:
            used_model = True
            for key, value in filled.items():
                fields.setdefault(key, value)

    # Trip-level defaults are applied last and never override the sentence.
    for key, value in (defaults or {}).items():
        if value is not None:
            fields.setdefault(key, value)

    assumptions: list[str] = []
    if fields.pop("_flexible_assumed", False):
        assumptions.append(
            "read \"around\" as being flexible by two days either side of the date"
        )
    if fields.pop("_child_age_assumed", False):
        assumptions.append(
            f"no child age was given, so {ASSUMED_CHILD_AGE} was assumed - change it "
            "before booking, because the fare depends on it"
        )
    if fields.pop("_infants_mentioned", False):
        assumptions.append(
            "infants were mentioned but are not yet priced separately; they are not "
            "included in the traveller count"
        )
    if used_model:
        assumptions.append("a model was used to read the places or dates from the text")

    missing = [key for key in ("origin", "destination", "departure_date") if key not in fields]
    if missing:
        return ParsedSearch(
            fields=fields, missing=missing, assumptions=assumptions, used_model=used_model
        )

    try:
        criteria = FlightSearchCriteria.model_validate(fields)
    except Exception as exc:  # noqa: BLE001 - reported as an incomplete parse
        logger.info("parsed search failed validation", extra={"error": str(exc)})
        return ParsedSearch(
            fields=fields,
            missing=["criteria"],
            assumptions=assumptions + [f"the request could not be validated: {exc}"],
            used_model=used_model,
        )

    return ParsedSearch(
        criteria=criteria, fields=fields, assumptions=assumptions, used_model=used_model
    )


# The only fields a model is ever allowed to contribute. Money is absent on
# purpose and must stay absent: a fabricated ceiling filters real options out of
# a real search, and the traveller has no way to see that it happened.
_MODEL_MAY_SUPPLY = frozenset({"origin", "destination", "departure_date", "return_date"})


# ---- the model's narrow role -------------------------------------------
async def _model_fill(text: str, needed: list[str]) -> dict[str, Any]:
    """Ask the model for places and dates only.

    Every other field, and every amount, is dropped from the answer. The model
    is here because "a fortnight somewhere warm in the new year" defeats a
    regular expression, not because it should be deciding what a trip costs.
    """
    llm = get_llm_service()
    if not llm.available:
        return {}

    payload = await llm.complete_json(
        system=(
            "Extract travel search fields from the message. Return JSON with only "
            "these keys, omitting any you are not confident about: origin (city "
            "name), destination (city name), departure_date (YYYY-MM-DD), "
            "return_date (YYYY-MM-DD). Never guess a price, a budget or an "
            "airline. Never invent a date that the message does not imply."
        ),
        user=text,
        purpose="flight_search_parse",
    )
    if not payload:
        return {}

    allowed = {"origin", "destination", "departure_date", "return_date"}
    filled: dict[str, Any] = {}
    for key in allowed:
        if key not in needed and key != "return_date":
            continue
        value = payload.get(key)
        if not value or not isinstance(value, str):
            continue
        if key.endswith("_date"):
            try:
                filled[key] = date.fromisoformat(value.strip())
            except ValueError:
                continue
        else:
            filled[key] = value.strip()[:120]
    return filled


# ---- helpers ------------------------------------------------------------
def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return next((group for group in match.groups() if group), None)


def _hour_from(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    if not match:
        return None
    raw = _as_int(match.group(1))
    if raw is None:
        return None
    meridiem = (match.group(2) or "").lower()
    hour = raw % 12
    if meridiem == "pm":
        hour += 12
    elif not meridiem and raw <= 23:
        hour = raw
    return max(0, min(hour, 23))


def _airlines_in(text: str, pattern: re.Pattern[str]) -> list[str]:
    codes: list[str] = []
    for match in pattern.finditer(text):
        phrase = match.group(1).strip().lower()
        for name, code in _AIRLINE_NAMES.items():
            if phrase.startswith(name) or name in phrase:
                if code not in codes:
                    codes.append(code)
                break
    return codes


def _dates_from(text: str, reference: date) -> list[date]:
    """Dates mentioned in the text, in the order they appear.

    A month and day without a year means the next occurrence: "June 10" said in
    August means next June, not a date four months in the past.
    """
    found: list[tuple[int, date]] = []

    for match in _ISO_DATE.finditer(text):
        try:
            found.append((match.start(), date(int(match.group(1)), int(match.group(2)), int(match.group(3)))))
        except ValueError:
            continue

    for pattern, month_first in ((_MONTH_DAY, True), (_DAY_MONTH, False)):
        for match in pattern.finditer(text):
            month_raw = match.group(1) if month_first else match.group(2)
            day_raw = match.group(2) if month_first else match.group(1)
            month = _MONTHS.get(month_raw.lower())
            if not month:
                continue
            try:
                day = int(day_raw)
                candidate = date(reference.year, month, day)
            except ValueError:
                continue
            if candidate < reference:
                try:
                    candidate = date(reference.year + 1, month, day)
                except ValueError:
                    continue
            found.append((match.start(), candidate))

    ordered = [value for _, value in sorted(found, key=lambda pair: pair[0])]
    deduped: list[date] = []
    for value in ordered:
        if value not in deduped:
            deduped.append(value)
    return deduped[:2]


assert datetime  # imported for callers that pass an aware reference date

__all__ = ["ParsedSearch", "parse", "parse_deterministic"]
