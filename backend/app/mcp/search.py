"""Search MCP adapter (Tavily or any configured search provider).

Exposes ``web_search`` and ``search_hotels``. Hotel results derived from
search snippets are labelled ``SEARCH_DERIVED``; nightly rates that come from
JourneyMesh's own cost model are labelled ``ESTIMATE``. The two are never
mixed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.constants import SOURCE_ESTIMATE, SOURCE_SEARCH_DERIVED
from app.observability.logging import get_logger

logger = get_logger("journeymesh.mcp.search")

TAVILY_ENDPOINT = "https://api.tavily.com/search"

# Nightly rate bands per travel style, in USD. Used only to produce clearly
# labelled estimates when no live rate is available.
_STYLE_NIGHTLY = {
    "budget": (28.0, 55.0),
    "comfort": (70.0, 130.0),
    "luxury": (220.0, 420.0),
    "adventure": (45.0, 90.0),
    "family": (90.0, 160.0),
    "business": (120.0, 210.0),
    "relaxed": (95.0, 175.0),
}

_PREFERENCE_NIGHTLY = {
    "hostel": (18.0, 40.0),
    "guesthouse": (32.0, 65.0),
    "three_star": (60.0, 110.0),
    "four_star": (110.0, 190.0),
    "five_star": (230.0, 460.0),
    "apartment": (75.0, 150.0),
    "resort": (160.0, 320.0),
}

_AREA_TEMPLATES = (
    ("City centre", "walkable, close to transit and restaurants"),
    ("Waterfront district", "quieter evenings, good for families"),
    ("Old town", "historic streets and local food"),
    ("Business district", "reliable transport links, newer buildings"),
    ("Near the main park", "green space and space for children to run"),
)

_AMENITY_POOL = (
    "free wifi",
    "breakfast included",
    "air conditioning",
    "family rooms",
    "24h reception",
    "airport shuttle",
    "swimming pool",
    "kitchenette",
    "laundry",
    "fitness centre",
)

_PRICE_IN_TEXT = re.compile(r"(?:US)?\$\s?(\d{2,4})(?:\s?(?:per night|/night|a night))?", re.IGNORECASE)


async def web_search(*, query: str, max_results: int = 5) -> dict[str, Any]:
    """Tool implementation for ``web_search``."""
    settings = get_settings()
    if not settings.tavily_api_key:
        return {
            "query": query,
            "results": [],
            "source": "UNAVAILABLE",
            "note": "No search provider is configured; JourneyMesh used its own knowledge instead.",
        }

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max(1, min(int(max_results), 10)),
        "search_depth": "basic",
        "include_answer": False,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
            response = await client.post(TAVILY_ENDPOINT, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("search provider failed", extra={"error": str(exc)})
        return {
            "query": query,
            "results": [],
            "source": "UNAVAILABLE",
            "note": "The search provider was unavailable.",
        }

    results = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": item.get("content"),
            "score": item.get("score"),
        }
        for item in (data.get("results") or [])
    ]
    return {
        "query": query,
        "results": results,
        "source": SOURCE_SEARCH_DERIVED,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def _band(travel_style: str | None, hotel_preference: str | None) -> tuple[float, float]:
    if hotel_preference and hotel_preference in _PREFERENCE_NIGHTLY:
        return _PREFERENCE_NIGHTLY[hotel_preference]
    return _STYLE_NIGHTLY.get(travel_style or "comfort", _STYLE_NIGHTLY["comfort"])


def _extract_price(text: str | None) -> float | None:
    if not text:
        return None
    match = _PRICE_IN_TEXT.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if 10 <= value <= 2000 else None


def _reference_hotels(
    destination: str,
    travel_style: str | None,
    hotel_preference: str | None,
    max_price_per_night: float | None,
    travelers: int,
) -> list[dict[str, Any]]:
    low, high = _band(travel_style, hotel_preference)
    if max_price_per_night:
        high = min(high, float(max_price_per_night))
        low = min(low, high * 0.75)

    seed = sum(ord(char) for char in destination.lower()) if destination else 7
    options: list[dict[str, Any]] = []
    steps = 4
    for index in range(steps):
        area, area_note = _AREA_TEMPLATES[(seed + index) % len(_AREA_TEMPLATES)]
        ratio = index / max(steps - 1, 1)
        nightly = round(low + (high - low) * ratio, 2)
        amenities = [
            _AMENITY_POOL[(seed + index + offset) % len(_AMENITY_POOL)] for offset in range(4)
        ]
        family = travelers > 2 or (travel_style == "family")
        if family and "family rooms" not in amenities:
            amenities[-1] = "family rooms"
        options.append(
            {
                "name": f"{area} stay {index + 1} - {destination}",
                "area": area,
                "category": hotel_preference or travel_style or "comfort",
                "rating": round(3.8 + 0.3 * ratio, 1),
                "review_summary": f"{area_note.capitalize()}.",
                "price_per_night": nightly,
                "currency": "USD",
                "price_source": SOURCE_ESTIMATE,
                "amenities": sorted(set(amenities)),
                "family_friendly": family,
                "distance_to_centre_km": round(1.0 + 1.4 * index, 1),
                "why_recommended": (
                    f"Matches a {travel_style or 'comfort'} budget in {destination} "
                    f"and sits in the {area.lower()}."
                ),
                "reference_url": None,
                "provenance": {
                    "source": SOURCE_ESTIMATE,
                    "provider": "journeymesh_reference",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "note": "nightly rate band for the selected travel style",
                },
            }
        )
    return options


async def search_hotels(
    *,
    destination: str,
    max_price_per_night: float | None = None,
    travel_style: str | None = None,
    travelers: int = 1,
) -> dict[str, Any]:
    """Tool implementation for ``search_hotels``."""
    settings = get_settings()
    notes: list[str] = []
    options: list[dict[str, Any]] = []
    source = SOURCE_ESTIMATE

    if settings.tavily_api_key:
        query = f"best hotels in {destination}"
        if travel_style:
            query += f" for {travel_style} travellers"
        if max_price_per_night:
            query += f" under ${int(max_price_per_night)} per night"

        found = await web_search(query=query, max_results=6)
        for item in found.get("results", [])[:6]:
            nightly = _extract_price(item.get("snippet")) or _extract_price(item.get("title"))
            options.append(
                {
                    "name": (item.get("title") or "Recommended stay").split(" - ")[0][:120],
                    "area": destination,
                    "category": travel_style or "comfort",
                    "rating": None,
                    "review_summary": (item.get("snippet") or "")[:280] or None,
                    "price_per_night": nightly,
                    "currency": "USD" if nightly else None,
                    "price_source": SOURCE_SEARCH_DERIVED if nightly else "UNAVAILABLE",
                    "amenities": [],
                    "family_friendly": travelers > 2,
                    "distance_to_centre_km": None,
                    "why_recommended": "Surfaced by live destination research.",
                    "reference_url": item.get("url"),
                    "provenance": {
                        "source": SOURCE_SEARCH_DERIVED,
                        "provider": "tavily",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "note": "derived from a public search result snippet",
                    },
                }
            )
        if options:
            source = SOURCE_SEARCH_DERIVED
            notes.append("Hotel candidates were surfaced from live destination research.")
        else:
            notes.append("Live search returned no usable hotel candidates.")

    if not options:
        options = _reference_hotels(
            destination, travel_style, None, max_price_per_night, travelers
        )
        notes.append(
            "Nightly rates below are JourneyMesh planning estimates, not live availability."
        )

    if max_price_per_night:
        within = [o for o in options if (o.get("price_per_night") or 0) <= max_price_per_night]
        if within:
            options = within
        else:
            notes.append(
                f"No candidate met the {max_price_per_night:.0f} per night ceiling; "
                "the closest options are shown."
            )
            options.sort(key=lambda o: o.get("price_per_night") or 1e9)

    return {
        "destination": destination,
        "options": options,
        "currency": "USD",
        "source": source,
        "notes": notes,
    }


TOOLS = {
    "web_search": web_search,
    "search_hotels": search_hotels,
}
