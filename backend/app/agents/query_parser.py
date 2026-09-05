"""Read planning constraints out of the request sentence.

The planner asks for one sentence and marks every other field optional, so a
request routinely arrives as a query and nothing else. Without this module the
structured fields stay empty, and an empty ``destination`` is not a small gap:
the hotel agent skips, the itinerary has nowhere to put its days, and the
budget agent prices a journey to nowhere.

The extraction is deterministic. Places are matched against the same airport
vocabulary the aviation adapter already ships, plus the countries those
airports belong to, so a match is a place this system can actually plan for
rather than any capitalised word. Everything else - travellers, budget,
travel style, interests - is read from vocabulary the schemas already define.

Nothing here overwrites a value the traveller typed into a field. A field that
was filled in is an instruction; this module only fills in the blanks.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any

from app.core.constants import INTERESTS, SUPPORTED_CURRENCIES, TRAVEL_STYLES
from app.mcp.aviation import AIRPORTS

__all__ = ["extract_constraints", "places_from_text"]

# ---- place vocabulary ------------------------------------------------------
# Aliases for places people name differently from the airport table. The value
# is what the rest of the system will see, so it has to be a key the aviation
# adapter can resolve, or a country it knows.
_PLACE_ALIASES: dict[str, str] = {
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "emirates": "United Arab Emirates",
    "usa": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "turkey": "Turkiye",
    "korea": "South Korea",
    "holland": "Netherlands",
    "bangla": "Bangladesh",
}

# Words that are place names in the vocabulary but are far more often used as
# ordinary words in a travel sentence. Matching them costs more than it gains.
_PLACE_STOPWORDS = frozenset({"us"})


@cache
def _place_vocabulary() -> dict[str, str]:
    """Lowercased phrase -> the name to store, longest phrase winning."""
    vocabulary: dict[str, str] = {}
    for city, record in AIRPORTS.items():
        vocabulary[city.lower()] = city.title()
        country = record.get("country")
        if country:
            vocabulary[country.lower()] = country
    for alias, canonical in _PLACE_ALIASES.items():
        vocabulary.setdefault(alias, canonical)
    return vocabulary


@cache
def _place_pattern() -> re.Pattern[str]:
    phrases = sorted(_place_vocabulary(), key=len, reverse=True)
    joined = "|".join(re.escape(phrase) for phrase in phrases)
    return re.compile(rf"(?<![\w-])({joined})(?![\w-])", re.IGNORECASE)


# A place is an origin when one of these introduces it, and a destination when
# one of the destination markers does. "from Dhaka to Singapore" and "a Goa
# trip from Kolkata" both resolve correctly from the marker alone.
_ORIGIN_MARKER = re.compile(r"\b(from|leaving|departing|starting(?:\s+from)?|out\s+of)\s*$", re.I)
_DESTINATION_MARKER = re.compile(
    r"\b(to|in|at|into|visit(?:ing)?|explore|see|toward|towards|around)\s*$", re.I
)


def places_from_text(text: str) -> tuple[str | None, str | None]:
    """Return ``(origin, destination)`` as far as the sentence states them."""
    if not text:
        return None, None

    vocabulary = _place_vocabulary()
    origin: str | None = None
    destination: str | None = None
    unmarked: list[str] = []

    for match in _place_pattern().finditer(text):
        phrase = match.group(1).lower()
        if phrase in _PLACE_STOPWORDS:
            continue
        name = vocabulary.get(phrase)
        if not name:
            continue

        before = text[: match.start()]
        if _ORIGIN_MARKER.search(before):
            origin = origin or name
        elif _DESTINATION_MARKER.search(before):
            destination = destination or name
        elif name not in unmarked:
            # "a 7-day India trip from Bangladesh" - the destination carries no
            # preposition at all, which is why an unmarked place is a candidate
            # rather than a discard.
            unmarked.append(name)

    for name in unmarked:
        if destination is None and name != origin:
            destination = name
        elif origin is None and name != destination:
            origin = name

    if origin and destination and origin.lower() == destination.lower():
        origin = None
    return origin, destination


# ---- travellers ------------------------------------------------------------
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUMBER = r"(\d{1,2}|" + "|".join(_WORD_NUMBERS) + r")"
_TRAVELLERS = re.compile(
    rf"\b(?:family|group|party)\s+of\s+{_NUMBER}\b"
    rf"|\b{_NUMBER}\s*(?:people|persons?|travell?ers?|adults?|of\s+us)\b",
    re.IGNORECASE,
)
_SOLO = re.compile(r"\b(solo|alone|by\s+myself|just\s+me)\b", re.IGNORECASE)
_COUPLE = re.compile(r"\b(couple|honeymoon|my\s+(?:wife|husband|partner)\s+and\s+i)\b", re.I)


def _travellers_from_text(text: str) -> int | None:
    match = _TRAVELLERS.search(text)
    if match:
        raw = next((group for group in match.groups() if group), None)
        if raw:
            value = _WORD_NUMBERS.get(raw.lower()) or int(raw)
            if 1 <= value <= 20:
                return value
    if _COUPLE.search(text):
        return 2
    if _SOLO.search(text):
        return 1
    return None


# ---- budget ----------------------------------------------------------------
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "৳": "BDT", "¥": "JPY"}
_BUDGET = re.compile(
    r"(?:budget\s+(?:of|is|around|about|near)?\s*|under\s*|below\s*|within\s*|up\s+to\s*|"
    r"no\s+more\s+than\s*|max(?:imum)?\s+(?:of\s+)?)?"
    r"([$€£₹৳¥]|\b(?:usd|eur|gbp|inr|bdt|aed|sgd|jpy|aud|taka|rupees?|dollars?)\b)?\s*"
    r"(\d[\d,]*(?:\.\d+)?)\s*"
    r"(k\b|thousand\b)?\s*"
    r"([$€£₹৳¥]|\b(?:usd|eur|gbp|inr|bdt|aed|sgd|jpy|aud|taka|rupees?|dollars?)\b)?",
    re.IGNORECASE,
)
_BUDGET_CONTEXT = re.compile(
    r"\b(budget|cost|spend|spending|afford|price|under|below|within|up\s+to|max(?:imum)?)\b",
    re.IGNORECASE,
)
_CURRENCY_WORDS = {
    "taka": "BDT",
    "rupee": "INR",
    "rupees": "INR",
    "dollar": "USD",
    "dollars": "USD",
}


def _currency_from(token: str | None) -> str | None:
    if not token:
        return None
    cleaned = token.strip().lower()
    if cleaned in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[cleaned]
    if cleaned.upper() in SUPPORTED_CURRENCIES:
        return cleaned.upper()
    return _CURRENCY_WORDS.get(cleaned)


def _budget_from_text(text: str) -> tuple[float | None, str | None]:
    """The stated total budget, and the currency it was stated in."""
    for match in _BUDGET.finditer(text):
        leading, amount_raw, scale, trailing = match.groups()
        if not amount_raw:
            continue
        currency = _currency_from(leading) or _currency_from(trailing)
        window = text[max(0, match.start() - 30) : match.end()]
        # A bare number in a travel sentence is usually a duration or a party
        # size. It only becomes a budget when a symbol or the words around it
        # say so.
        if currency is None and not _BUDGET_CONTEXT.search(window):
            continue
        try:
            amount = float(amount_raw.replace(",", ""))
        except ValueError:
            continue
        if scale:
            amount *= 1000
        if amount < 10:  # "under 3 days" style false positives
            continue
        return amount, currency
    return None, None


# ---- style and interests ---------------------------------------------------
_STYLE_TERMS: dict[str, tuple[str, ...]] = {
    # "budget" alone is excluded on purpose: in "estimated budget" and "budget
    # of $2000" it names an amount, not a way of travelling. Only the phrases
    # that can only mean a style are matched.
    "budget": ("cheap", "affordable", "backpacking", "shoestring", "on a budget", "budget-friendly"),
    "comfort": ("comfortable", "mid-range", "midrange"),
    "luxury": ("luxury", "luxurious", "premium", "five star", "5 star"),
    "adventure": ("adventure", "adventurous", "trekking", "hiking", "diving"),
    "family": ("family", "kids", "children", "child-friendly", "child friendly"),
    "business": ("business", "work trip", "conference", "meetings"),
    "relaxed": ("relaxing", "relaxed", "leisurely", "unwind", "chill"),
}

# Most specific first. A sentence often carries two of these - "a relaxing
# family trip" - and the one that shapes the plan most is the one to keep.
_STYLE_PRIORITY = ("business", "family", "luxury", "adventure", "relaxed", "budget", "comfort")

_INTEREST_TERMS: dict[str, tuple[str, ...]] = {
    "food": ("food", "cuisine", "restaurants", "eating", "street food", "culinary"),
    "nature": ("nature", "wildlife", "mountains", "parks", "scenery", "landscape"),
    "history": ("history", "historical", "heritage", "ruins", "monuments", "sightseeing"),
    "culture": ("culture", "cultural", "museums", "temples", "art", "festivals"),
    "shopping": ("shopping", "markets", "bazaar", "malls"),
    "beaches": ("beach", "beaches", "island", "islands", "snorkel", "coastal"),
    "nightlife": ("nightlife", "clubs", "bars", "party"),
    "photography": ("photography", "photos", "photographic"),
    "technology": ("technology", "tech", "gadgets", "innovation"),
    "family_activities": ("family activities", "kid-friendly", "theme park", "playground"),
}


def _vocabulary_hits(text: str, terms: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = text.lower()
    return [
        key
        for key, phrases in terms.items()
        if any(re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", lowered) for p in phrases)
    ]


def _style_from_text(text: str) -> str | None:
    hits = {style for style in _vocabulary_hits(text, _STYLE_TERMS) if style in TRAVEL_STYLES}
    return next((style for style in _STYLE_PRIORITY if style in hits), None)


def _interests_from_text(text: str) -> list[str]:
    return [item for item in _vocabulary_hits(text, _INTEREST_TERMS) if item in INTERESTS]


# ---- entry point -----------------------------------------------------------
def extract_constraints(query: str, constraints: dict[str, Any]) -> dict[str, Any]:
    """Constraint values the sentence states and the form did not.

    Returns only the keys worth writing: a value already present in
    ``constraints`` is never replaced, because a filled-in field outranks a
    reading of the prose.
    """
    updates: dict[str, Any] = {}
    if not query:
        return updates

    origin, destination = places_from_text(query)
    if destination and not constraints.get("destination"):
        updates["destination"] = destination
    if origin and not constraints.get("origin"):
        # Never let an inferred origin equal the destination that will be used.
        chosen_destination = updates.get("destination") or constraints.get("destination")
        if not chosen_destination or origin.lower() != str(chosen_destination).lower():
            updates["origin"] = origin

    travellers = _travellers_from_text(query)
    if travellers and int(constraints.get("travelers") or 1) == 1:
        updates["travelers"] = travellers

    if constraints.get("budget") is None:
        amount, currency = _budget_from_text(query)
        if amount is not None:
            updates["budget"] = amount
            # USD is the form's default, so it is the only value a stated
            # currency is allowed to override. Anything else was chosen.
            if currency and str(constraints.get("currency") or "USD").upper() == "USD":
                updates["currency"] = currency

    if not constraints.get("travel_style"):
        style = _style_from_text(query)
        if style:
            updates["travel_style"] = style

    if not constraints.get("interests"):
        interests = _interests_from_text(query)
        if interests:
            updates["interests"] = interests

    return updates
