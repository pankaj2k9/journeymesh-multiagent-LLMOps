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
    "sylhet": {"iata": "ZYL", "name": "Osmani International", "country": "Bangladesh"},
    "cox's bazar": {"iata": "CXB", "name": "Cox's Bazar Airport", "country": "Bangladesh"},
    "jessore": {"iata": "JSR", "name": "Jessore Airport", "country": "Bangladesh"},
    "rajshahi": {"iata": "RJH", "name": "Shah Makhdum Airport", "country": "Bangladesh"},
    # Destinations with no airport of their own, resolved to the nearest one, so
    # a traveller can pick "Bandarban" and the flight agent still finds a route.
    "barisal": {"iata": "BZL", "name": "Barisal Airport", "country": "Bangladesh"},
    "khulna": {"iata": "JSR", "name": "Jessore Airport", "country": "Bangladesh"},
    "bandarban": {"iata": "CGP", "name": "Shah Amanat International", "country": "Bangladesh"},
    "rangamati": {"iata": "CGP", "name": "Shah Amanat International", "country": "Bangladesh"},
    "sajek valley": {"iata": "CGP", "name": "Shah Amanat International", "country": "Bangladesh"},
    "saint martin's island": {"iata": "CXB", "name": "Cox's Bazar Airport", "country": "Bangladesh"},
    "st. martin's island": {"iata": "CXB", "name": "Cox's Bazar Airport", "country": "Bangladesh"},
    "sreemangal": {"iata": "ZYL", "name": "Osmani International", "country": "Bangladesh"},
    "srimangal": {"iata": "ZYL", "name": "Osmani International", "country": "Bangladesh"},
    "kuakata": {"iata": "BZL", "name": "Barisal Airport", "country": "Bangladesh"},
    "kolkata": {"iata": "CCU", "name": "Netaji Subhas Chandra Bose International", "country": "India"},
    "delhi": {"iata": "DEL", "name": "Indira Gandhi International", "country": "India"},
    "agra": {"iata": "AGR", "name": "Agra Airport", "country": "India"},
    "new delhi": {"iata": "DEL", "name": "Indira Gandhi International", "country": "India"},
    "mumbai": {"iata": "BOM", "name": "Chhatrapati Shivaji Maharaj International", "country": "India"},
    "bengaluru": {"iata": "BLR", "name": "Kempegowda International", "country": "India"},
    "bangalore": {"iata": "BLR", "name": "Kempegowda International", "country": "India"},
    "chennai": {"iata": "MAA", "name": "Chennai International", "country": "India"},
    "goa": {"iata": "GOI", "name": "Goa International", "country": "India"},
    "hyderabad": {"iata": "HYD", "name": "Rajiv Gandhi International", "country": "India"},
    "ahmedabad": {"iata": "AMD", "name": "Sardar Vallabhbhai Patel International", "country": "India"},
    "pune": {"iata": "PNQ", "name": "Pune Airport", "country": "India"},
    "jaipur": {"iata": "JAI", "name": "Jaipur International", "country": "India"},
    "udaipur": {"iata": "UDR", "name": "Maharana Pratap Airport", "country": "India"},
    "kochi": {"iata": "COK", "name": "Cochin International", "country": "India"},
    "thiruvananthapuram": {"iata": "TRV", "name": "Thiruvananthapuram International", "country": "India"},
    "varanasi": {"iata": "VNS", "name": "Lal Bahadur Shastri International", "country": "India"},
    "lucknow": {"iata": "LKO", "name": "Chaudhary Charan Singh International", "country": "India"},
    "amritsar": {"iata": "ATQ", "name": "Sri Guru Ram Dass Jee International", "country": "India"},
    "srinagar": {"iata": "SXR", "name": "Sheikh ul-Alam International", "country": "India"},
    "leh": {"iata": "IXL", "name": "Kushok Bakula Rimpochee Airport", "country": "India"},
    "guwahati": {"iata": "GAU", "name": "Lokpriya Gopinath Bordoloi International", "country": "India"},
    "bagdogra": {"iata": "IXB", "name": "Bagdogra Airport", "country": "India"},
    "port blair": {"iata": "IXZ", "name": "Veer Savarkar International", "country": "India"},
    "kathmandu": {"iata": "KTM", "name": "Tribhuvan International", "country": "Nepal"},
    "pokhara": {"iata": "PKR", "name": "Pokhara International", "country": "Nepal"},
    "colombo": {"iata": "CMB", "name": "Bandaranaike International", "country": "Sri Lanka"},
    "male": {"iata": "MLE", "name": "Velana International", "country": "Maldives"},
    "malé": {"iata": "MLE", "name": "Velana International", "country": "Maldives"},
    "bangkok": {"iata": "BKK", "name": "Suvarnabhumi", "country": "Thailand"},
    "phuket": {"iata": "HKT", "name": "Phuket International", "country": "Thailand"},
    "chiang mai": {"iata": "CNX", "name": "Chiang Mai International", "country": "Thailand"},
    "singapore": {"iata": "SIN", "name": "Changi", "country": "Singapore"},
    "kuala lumpur": {"iata": "KUL", "name": "Kuala Lumpur International", "country": "Malaysia"},
    "penang": {"iata": "PEN", "name": "Penang International", "country": "Malaysia"},
    "bali": {"iata": "DPS", "name": "Ngurah Rai International", "country": "Indonesia"},
    "jakarta": {"iata": "CGK", "name": "Soekarno-Hatta International", "country": "Indonesia"},
    "hanoi": {"iata": "HAN", "name": "Noi Bai International", "country": "Vietnam"},
    "ho chi minh city": {"iata": "SGN", "name": "Tan Son Nhat International", "country": "Vietnam"},
    "da nang": {"iata": "DAD", "name": "Da Nang International", "country": "Vietnam"},
    "tokyo": {"iata": "HND", "name": "Haneda", "country": "Japan"},
    "kyoto": {"iata": "KIX", "name": "Kansai International", "country": "Japan"},
    "osaka": {"iata": "KIX", "name": "Kansai International", "country": "Japan"},
    "seoul": {"iata": "ICN", "name": "Incheon International", "country": "South Korea"},
    "hong kong": {"iata": "HKG", "name": "Hong Kong International", "country": "Hong Kong"},
    "shanghai": {"iata": "PVG", "name": "Shanghai Pudong International", "country": "China"},
    "beijing": {"iata": "PEK", "name": "Beijing Capital International", "country": "China"},
    "guangzhou": {"iata": "CAN", "name": "Guangzhou Baiyun International", "country": "China"},
    "shenzhen": {"iata": "SZX", "name": "Shenzhen Bao'an International", "country": "China"},
    "chengdu": {"iata": "TFU", "name": "Chengdu Tianfu International", "country": "China"},
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
    # ---- more destinations: each with its own airport, or the nearest one ----
    # India
    "shimla": {"iata": "SLV", "name": "Shimla Airport", "country": "India"},
    "manali": {"iata": "KUU", "name": "Kullu-Manali Airport", "country": "India"},
    "dehradun": {"iata": "DED", "name": "Dehradun Airport", "country": "India"},
    "rishikesh": {"iata": "DED", "name": "Dehradun Airport", "country": "India"},
    "haridwar": {"iata": "DED", "name": "Dehradun Airport", "country": "India"},
    "darjeeling": {"iata": "IXB", "name": "Bagdogra Airport", "country": "India"},
    "gangtok": {"iata": "IXB", "name": "Bagdogra Airport", "country": "India"},
    "mysuru": {"iata": "MYQ", "name": "Mysore Airport", "country": "India"},
    "coimbatore": {"iata": "CJB", "name": "Coimbatore International", "country": "India"},
    "ooty": {"iata": "CJB", "name": "Coimbatore International", "country": "India"},
    "munnar": {"iata": "COK", "name": "Cochin International", "country": "India"},
    "alappuzha": {"iata": "COK", "name": "Cochin International", "country": "India"},
    "jodhpur": {"iata": "JDH", "name": "Jodhpur Airport", "country": "India"},
    "jaisalmer": {"iata": "JSA", "name": "Jaisalmer Airport", "country": "India"},
    "khajuraho": {"iata": "HJR", "name": "Khajuraho Airport", "country": "India"},
    "hampi": {"iata": "VDY", "name": "Jindal Vijaynagar Airport", "country": "India"},
    "shillong": {"iata": "SHL", "name": "Shillong Airport", "country": "India"},
    # Sri Lanka
    "kandy": {"iata": "CMB", "name": "Bandaranaike International", "country": "Sri Lanka"},
    "sigiriya": {"iata": "CMB", "name": "Bandaranaike International", "country": "Sri Lanka"},
    "galle": {"iata": "CMB", "name": "Bandaranaike International", "country": "Sri Lanka"},
    "ella": {"iata": "CMB", "name": "Bandaranaike International", "country": "Sri Lanka"},
    "nuwara eliya": {"iata": "CMB", "name": "Bandaranaike International", "country": "Sri Lanka"},
    # Thailand
    "krabi": {"iata": "KBV", "name": "Krabi International", "country": "Thailand"},
    "pattaya": {"iata": "UTP", "name": "U-Tapao International", "country": "Thailand"},
    # Malaysia
    "langkawi": {"iata": "LGK", "name": "Langkawi International", "country": "Malaysia"},
    "malacca": {"iata": "KUL", "name": "Kuala Lumpur International", "country": "Malaysia"},
    # Philippines
    "manila": {"iata": "MNL", "name": "Ninoy Aquino International", "country": "Philippines"},
    "cebu": {"iata": "CEB", "name": "Mactan-Cebu International", "country": "Philippines"},
    "caticlan": {"iata": "MPH", "name": "Godofredo P. Ramos Airport", "country": "Philippines"},
    "boracay": {"iata": "MPH", "name": "Godofredo P. Ramos Airport", "country": "Philippines"},
    "puerto princesa": {"iata": "PPS", "name": "Puerto Princesa International", "country": "Philippines"},
    "el nido": {"iata": "PPS", "name": "Puerto Princesa International", "country": "Philippines"},
    "bohol": {"iata": "TAG", "name": "Bohol-Panglao International", "country": "Philippines"},
    # Vietnam
    "ha long": {"iata": "HAN", "name": "Noi Bai International", "country": "Vietnam"},
    "hoi an": {"iata": "DAD", "name": "Da Nang International", "country": "Vietnam"},
    "hue": {"iata": "HUI", "name": "Phu Bai International", "country": "Vietnam"},
    # Indonesia
    "yogyakarta": {"iata": "YIA", "name": "Yogyakarta International", "country": "Indonesia"},
    "lombok": {"iata": "LOP", "name": "Lombok International", "country": "Indonesia"},
    "labuan bajo": {"iata": "LBJ", "name": "Komodo Airport", "country": "Indonesia"},
    # China
    "xi'an": {"iata": "XIY", "name": "Xi'an Xianyang International", "country": "China"},
    "guilin": {"iata": "KWL", "name": "Guilin Liangjiang International", "country": "China"},
    "zhangjiajie": {"iata": "DYG", "name": "Zhangjiajie Hehua International", "country": "China"},
    "hangzhou": {"iata": "HGH", "name": "Hangzhou Xiaoshan International", "country": "China"},
    # Egypt
    "luxor": {"iata": "LXR", "name": "Luxor International", "country": "Egypt"},
    "aswan": {"iata": "ASW", "name": "Aswan International", "country": "Egypt"},
    "hurghada": {"iata": "HRG", "name": "Hurghada International", "country": "Egypt"},
    "sharm el sheikh": {"iata": "SSH", "name": "Sharm El Sheikh International", "country": "Egypt"},
    "alexandria": {"iata": "HBE", "name": "Borg El Arab International", "country": "Egypt"},
    # Bahrain
    "manama": {"iata": "BAH", "name": "Bahrain International", "country": "Bahrain"},
    # Turkiye
    "cappadocia": {"iata": "NAV", "name": "Nevsehir Kapadokya Airport", "country": "Turkiye"},
    "antalya": {"iata": "AYT", "name": "Antalya Airport", "country": "Turkiye"},
    "denizli": {"iata": "DNZ", "name": "Denizli Cardak Airport", "country": "Turkiye"},
    "pamukkale": {"iata": "DNZ", "name": "Denizli Cardak Airport", "country": "Turkiye"},
    "izmir": {"iata": "ADB", "name": "Izmir Adnan Menderes Airport", "country": "Turkiye"},
    # Nepal
    "chitwan": {"iata": "BHR", "name": "Bharatpur Airport", "country": "Nepal"},
    "lumbini": {"iata": "BWA", "name": "Gautam Buddha International", "country": "Nepal"},
    "nagarkot": {"iata": "KTM", "name": "Tribhuvan International", "country": "Nepal"},
    "bhaktapur": {"iata": "KTM", "name": "Tribhuvan International", "country": "Nepal"},
    "lukla": {"iata": "LUA", "name": "Tenzing-Hillary Airport", "country": "Nepal"},
    # Bhutan
    "paro": {"iata": "PBH", "name": "Paro International", "country": "Bhutan"},
    "thimphu": {"iata": "PBH", "name": "Paro International", "country": "Bhutan"},
    # Spain
    "madrid": {"iata": "MAD", "name": "Adolfo Suarez Madrid-Barajas", "country": "Spain"},
    "seville": {"iata": "SVQ", "name": "Seville Airport", "country": "Spain"},
    "granada": {"iata": "GRX", "name": "Federico Garcia Lorca Granada Airport", "country": "Spain"},
    "malaga": {"iata": "AGP", "name": "Malaga Airport", "country": "Spain"},
    "valencia": {"iata": "VLC", "name": "Valencia Airport", "country": "Spain"},
    # Portugal
    "lisbon": {"iata": "LIS", "name": "Humberto Delgado Airport", "country": "Portugal"},
    "sintra": {"iata": "LIS", "name": "Humberto Delgado Airport", "country": "Portugal"},
    "porto": {"iata": "OPO", "name": "Francisco Sa Carneiro Airport", "country": "Portugal"},
    "faro": {"iata": "FAO", "name": "Faro Airport", "country": "Portugal"},
    "madeira": {"iata": "FNC", "name": "Madeira Airport", "country": "Portugal"},
    # Italy
    "venice": {"iata": "VCE", "name": "Venice Marco Polo Airport", "country": "Italy"},
    "florence": {"iata": "FLR", "name": "Florence Airport", "country": "Italy"},
    "milan": {"iata": "MXP", "name": "Milan Malpensa Airport", "country": "Italy"},
    "naples": {"iata": "NAP", "name": "Naples International", "country": "Italy"},
    "amalfi": {"iata": "NAP", "name": "Naples International", "country": "Italy"},
    "pisa": {"iata": "PSA", "name": "Pisa International", "country": "Italy"},
    "cinque terre": {"iata": "PSA", "name": "Pisa International", "country": "Italy"},
    # Switzerland
    "geneva": {"iata": "GVA", "name": "Geneva Airport", "country": "Switzerland"},
    "lucerne": {"iata": "ZRH", "name": "Zurich Airport", "country": "Switzerland"},
    "interlaken": {"iata": "ZRH", "name": "Zurich Airport", "country": "Switzerland"},
    "zermatt": {"iata": "GVA", "name": "Geneva Airport", "country": "Switzerland"},
    # East Asia
    "taipei": {"iata": "TPE", "name": "Taiwan Taoyuan International", "country": "Taiwan"},
    "hualien": {"iata": "HUN", "name": "Hualien Airport", "country": "Taiwan"},
    "macau": {"iata": "MFM", "name": "Macau International", "country": "Macau"},
    "ulaanbaatar": {"iata": "UBN", "name": "Chinggis Khaan International", "country": "Mongolia"},
    "busan": {"iata": "PUS", "name": "Gimhae International", "country": "South Korea"},
    "jeju": {"iata": "CJU", "name": "Jeju International", "country": "South Korea"},
    "sapporo": {"iata": "CTS", "name": "New Chitose Airport", "country": "Japan"},
    "hiroshima": {"iata": "HIJ", "name": "Hiroshima Airport", "country": "Japan"},
    "nara": {"iata": "KIX", "name": "Kansai International", "country": "Japan"},
    # South-East Asia
    "siem reap": {"iata": "SAI", "name": "Siem Reap-Angkor International", "country": "Cambodia"},
    "luang prabang": {"iata": "LPQ", "name": "Luang Prabang International", "country": "Laos"},
    "vientiane": {"iata": "VTE", "name": "Wattay International", "country": "Laos"},
    "bandar seri begawan": {"iata": "BWN", "name": "Brunei International", "country": "Brunei"},
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
