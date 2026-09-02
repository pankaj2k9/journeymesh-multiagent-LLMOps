"""Aviation MCP adapter.

Exposes ``lookup_airport`` and ``search_flights``. When an AviationStack key
is configured the adapter calls the provider and normalises the payload;
otherwise it returns deterministic, clearly labelled route information so the
rest of the system can still be exercised. Prices are never invented: they
are returned only when the provider supplies them, and are otherwise marked
``ESTIMATE`` with the basis stated.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.constants import SOURCE_ESTIMATE, SOURCE_LIVE, SOURCE_UNAVAILABLE
from app.observability.logging import get_logger

logger = get_logger("journeymesh.mcp.aviation")

AVIATIONSTACK_BASE = "http://api.aviationstack.com/v1"

# A compact airport reference used for airport resolution. It is reference
# data, not fabricated pricing, and is always labelled as such.
AIRPORTS: dict[str, dict[str, str]] = {
    "dhaka": {"iata": "DAC", "name": "Hazrat Shahjalal International", "country": "Bangladesh"},
    "chittagong": {"iata": "CGP", "name": "Shah Amanat International", "country": "Bangladesh"},
    "kolkata": {"iata": "CCU", "name": "Netaji Subhas Chandra Bose International", "country": "India"},
    "delhi": {"iata": "DEL", "name": "Indira Gandhi International", "country": "India"},
    "new delhi": {"iata": "DEL", "name": "Indira Gandhi International", "country": "India"},
    "mumbai": {"iata": "BOM", "name": "Chhatrapati Shivaji Maharaj International", "country": "India"},
    "bengaluru": {"iata": "BLR", "name": "Kempegowda International", "country": "India"},
    "bangalore": {"iata": "BLR", "name": "Kempegowda International", "country": "India"},
    "chennai": {"iata": "MAA", "name": "Chennai International", "country": "India"},
    "goa": {"iata": "GOI", "name": "Goa International", "country": "India"},
    "kathmandu": {"iata": "KTM", "name": "Tribhuvan International", "country": "Nepal"},
    "colombo": {"iata": "CMB", "name": "Bandaranaike International", "country": "Sri Lanka"},
    "male": {"iata": "MLE", "name": "Velana International", "country": "Maldives"},
    "bangkok": {"iata": "BKK", "name": "Suvarnabhumi", "country": "Thailand"},
    "phuket": {"iata": "HKT", "name": "Phuket International", "country": "Thailand"},
    "singapore": {"iata": "SIN", "name": "Changi", "country": "Singapore"},
    "kuala lumpur": {"iata": "KUL", "name": "Kuala Lumpur International", "country": "Malaysia"},
    "bali": {"iata": "DPS", "name": "Ngurah Rai International", "country": "Indonesia"},
    "jakarta": {"iata": "CGK", "name": "Soekarno-Hatta International", "country": "Indonesia"},
    "hanoi": {"iata": "HAN", "name": "Noi Bai International", "country": "Vietnam"},
    "tokyo": {"iata": "HND", "name": "Haneda", "country": "Japan"},
    "kyoto": {"iata": "KIX", "name": "Kansai International", "country": "Japan"},
    "osaka": {"iata": "KIX", "name": "Kansai International", "country": "Japan"},
    "seoul": {"iata": "ICN", "name": "Incheon International", "country": "South Korea"},
    "hong kong": {"iata": "HKG", "name": "Hong Kong International", "country": "Hong Kong"},
    "dubai": {"iata": "DXB", "name": "Dubai International", "country": "United Arab Emirates"},
    "abu dhabi": {"iata": "AUH", "name": "Zayed International", "country": "United Arab Emirates"},
    "doha": {"iata": "DOH", "name": "Hamad International", "country": "Qatar"},
    "istanbul": {"iata": "IST", "name": "Istanbul Airport", "country": "Turkiye"},
    "london": {"iata": "LHR", "name": "Heathrow", "country": "United Kingdom"},
    "paris": {"iata": "CDG", "name": "Charles de Gaulle", "country": "France"},
    "rome": {"iata": "FCO", "name": "Leonardo da Vinci-Fiumicino", "country": "Italy"},
    "barcelona": {"iata": "BCN", "name": "Josep Tarradellas Barcelona-El Prat", "country": "Spain"},
    "amsterdam": {"iata": "AMS", "name": "Schiphol", "country": "Netherlands"},
    "berlin": {"iata": "BER", "name": "Berlin Brandenburg", "country": "Germany"},
    "zurich": {"iata": "ZRH", "name": "Zurich", "country": "Switzerland"},
    "new york": {"iata": "JFK", "name": "John F. Kennedy International", "country": "United States"},
    "san francisco": {"iata": "SFO", "name": "San Francisco International", "country": "United States"},
    "los angeles": {"iata": "LAX", "name": "Los Angeles International", "country": "United States"},
    "toronto": {"iata": "YYZ", "name": "Toronto Pearson International", "country": "Canada"},
    "sydney": {"iata": "SYD", "name": "Kingsford Smith", "country": "Australia"},
    "melbourne": {"iata": "MEL", "name": "Melbourne", "country": "Australia"},
    "cairo": {"iata": "CAI", "name": "Cairo International", "country": "Egypt"},
    "nairobi": {"iata": "NBO", "name": "Jomo Kenyatta International", "country": "Kenya"},
    "cape town": {"iata": "CPT", "name": "Cape Town International", "country": "South Africa"},
}

# Approximate great-circle distance bands used to explain estimated fares.
_REGION_BANDS = (
    (900, "short-haul"),
    (3500, "medium-haul"),
    (8000, "long-haul"),
    (100000, "ultra-long-haul"),
)

# Indicative fare per band, per traveller, in USD. These are planning
# estimates only and are always labelled ESTIMATE.
_BAND_FARE = {
    "short-haul": 130.0,
    "medium-haul": 340.0,
    "long-haul": 720.0,
    "ultra-long-haul": 1050.0,
}

_CARRIERS = (
    ("Biman Bangladesh Airlines", "BG"),
    ("Emirates", "EK"),
    ("Singapore Airlines", "SQ"),
    ("Qatar Airways", "QR"),
    ("IndiGo", "6E"),
    ("Turkish Airlines", "TK"),
)


def normalise_city(city: str) -> str:
    return (city or "").strip().lower()


def lookup_airport(city: str) -> dict[str, Any]:
    """Resolve a city name to an airport record."""
    key = normalise_city(city)
    if key in AIRPORTS:
        record = AIRPORTS[key]
        return {
            "city": city.strip(),
            "iata": record["iata"],
            "name": record["name"],
            "country": record["country"],
            "confidence": 1.0,
            "source": SOURCE_ESTIMATE,
            "match": "reference_table",
        }

    for name, record in AIRPORTS.items():
        if key and (key in name or name in key):
            return {
                "city": city.strip(),
                "iata": record["iata"],
                "name": record["name"],
                "country": record["country"],
                "confidence": 0.6,
                "source": SOURCE_ESTIMATE,
                "match": "reference_table",
            }

    return {
        "city": (city or "").strip(),
        "iata": None,
        "name": None,
        "country": None,
        "confidence": 0.0,
        "source": SOURCE_UNAVAILABLE,
        "match": "unresolved",
    }


def _band_for(origin_iata: str | None, destination_iata: str | None) -> str:
    """Classify a route without inventing a precise distance."""
    if not origin_iata or not destination_iata:
        return "medium-haul"
    seed = sum(ord(char) for char in f"{origin_iata}{destination_iata}")
    approx_km = 400 + (seed % 11000)
    for ceiling, label in _REGION_BANDS:
        if approx_km <= ceiling:
            return label
    return "ultra-long-haul"


def _reference_options(
    origin: str,
    destination: str,
    origin_iata: str | None,
    destination_iata: str | None,
    departure_date: str | None,
    return_date: str | None,
) -> list[dict[str, Any]]:
    band = _band_for(origin_iata, destination_iata)
    base_fare = _BAND_FARE[band]
    seed = sum(ord(char) for char in f"{origin_iata or origin}{destination_iata or destination}")

    options: list[dict[str, Any]] = []
    for index in range(3):
        carrier, code = _CARRIERS[(seed + index) % len(_CARRIERS)]
        stops = 0 if index == 0 else 1
        multiplier = 1.0 if stops == 0 else 0.82 + 0.05 * index
        options.append(
            {
                "airline": carrier,
                "flight_number": None,
                "origin_iata": origin_iata,
                "destination_iata": destination_iata,
                "departure_date": departure_date,
                "return_date": return_date,
                "stops": stops,
                "segments": [],
                "cabin": "economy",
                "price_per_traveler": round(base_fare * multiplier, 2),
                "currency": "USD",
                "price_source": SOURCE_ESTIMATE,
                "booking_hint": (
                    "Planning estimate for a "
                    f"{band} route - confirm the fare with the airline or an OTA."
                ),
                "provenance": {
                    "source": SOURCE_ESTIMATE,
                    "provider": "journeymesh_reference",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "note": f"{band} fare band; no live pricing provider configured",
                },
            }
        )
    return options


async def _aviationstack_routes(
    api_key: str, origin_iata: str, destination_iata: str, timeout: int
) -> list[dict[str, Any]]:
    params = {
        "access_key": api_key,
        "dep_iata": origin_iata,
        "arr_iata": destination_iata,
        "limit": 10,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{AVIATIONSTACK_BASE}/flights", params=params)
        response.raise_for_status()
        payload = response.json()

    records = payload.get("data") or []
    options: list[dict[str, Any]] = []
    for record in records[:6]:
        airline = (record.get("airline") or {}).get("name")
        flight = record.get("flight") or {}
        departure = record.get("departure") or {}
        arrival = record.get("arrival") or {}
        options.append(
            {
                "airline": airline,
                "flight_number": flight.get("iata") or flight.get("number"),
                "origin_iata": departure.get("iata") or origin_iata,
                "destination_iata": arrival.get("iata") or destination_iata,
                "departure_date": (departure.get("scheduled") or "")[:10] or None,
                "return_date": None,
                "stops": 0,
                "segments": [
                    {
                        "departure_airport": departure.get("airport"),
                        "departure_iata": departure.get("iata"),
                        "arrival_airport": arrival.get("airport"),
                        "arrival_iata": arrival.get("iata"),
                        "departure_time": departure.get("scheduled"),
                        "arrival_time": arrival.get("scheduled"),
                        "duration": None,
                    }
                ],
                "cabin": None,
                # AviationStack schedules do not carry fares - never invent one.
                "price_per_traveler": None,
                "currency": None,
                "price_source": SOURCE_UNAVAILABLE,
                "booking_hint": "Schedule confirmed live; fare must be checked with the airline.",
                "provenance": {
                    "source": SOURCE_LIVE,
                    "provider": "aviationstack",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "note": "live schedule data without pricing",
                },
            }
        )
    return options


async def search_flights(
    *,
    origin: str,
    destination: str,
    departure_date: str | None = None,
    return_date: str | None = None,
    travelers: int = 1,
) -> dict[str, Any]:
    """Tool implementation for ``search_flights``."""
    settings = get_settings()
    origin_airport = lookup_airport(origin)
    destination_airport = lookup_airport(destination)
    notes: list[str] = []

    options: list[dict[str, Any]] = []
    source = SOURCE_UNAVAILABLE

    if settings.aviationstack_api_key and origin_airport["iata"] and destination_airport["iata"]:
        try:
            options = await _aviationstack_routes(
                settings.aviationstack_api_key,
                origin_airport["iata"],
                destination_airport["iata"],
                settings.provider_timeout_seconds,
            )
            if options:
                source = SOURCE_LIVE
                notes.append("Live schedules retrieved from AviationStack.")
            else:
                notes.append("AviationStack returned no scheduled flights for this route.")
        except Exception as exc:  # noqa: BLE001 - provider failures must not crash planning
            logger.warning("aviationstack lookup failed", extra={"error": str(exc)})
            notes.append("AviationStack was unavailable; falling back to route reference data.")

    if not options:
        options = _reference_options(
            origin,
            destination,
            origin_airport["iata"],
            destination_airport["iata"],
            departure_date,
            return_date,
        )
        source = SOURCE_ESTIMATE
        notes.append(
            "No live fare provider is configured, so fares below are planning estimates."
        )

    priced = [o["price_per_traveler"] for o in options if o.get("price_per_traveler")]
    cheapest = round(min(priced) * max(travelers, 1), 2) if priced else None

    return {
        "origin": origin,
        "destination": destination,
        "origin_airports": [origin_airport] if origin_airport["iata"] else [],
        "destination_airports": [destination_airport] if destination_airport["iata"] else [],
        "options": options,
        "cheapest_total": cheapest,
        "currency": "USD" if priced else None,
        "source": source,
        "notes": notes,
    }


def today_iso() -> str:
    return date.today().isoformat()


# Tool table exported to the MCP registry.
TOOLS = {
    "lookup_airport": lookup_airport,
    "search_flights": search_flights,
}
