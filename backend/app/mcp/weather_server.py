"""JourneyMesh custom Weather MCP server.

Two tools are exposed:

* ``get_current_weather(location)``
* ``get_weather_forecast(location, days)``

When ``OPENWEATHER_API_KEY`` is configured the tools return live observations
(``LIVE``). Otherwise they return a climate-normal projection derived from the
destination's climate zone, labelled ``ESTIMATE`` - useful for packing advice
and for choosing indoor or outdoor activities, and never presented as a live
forecast.

The module doubles as a standalone MCP server over stdio::

    python -m app.mcp.weather_server
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.constants import SOURCE_ESTIMATE, SOURCE_LIVE
from app.core.i18n import translate_all
from app.observability.logging import get_logger

logger = get_logger("journeymesh.mcp.weather")

OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"

# --- Climate reference ----------------------------------------------------
# monthly_high_c / monthly_low_c are January..December climate normals.
CLIMATE_ZONES: dict[str, dict[str, Any]] = {
    "tropical_monsoon": {
        "monthly_high_c": [26, 29, 33, 34, 34, 32, 31, 31, 32, 32, 30, 27],
        "monthly_low_c": [14, 17, 21, 24, 25, 26, 26, 26, 26, 24, 20, 15],
        "rain_chance": [5, 8, 15, 35, 60, 75, 80, 78, 65, 40, 15, 6],
        "humidity": 75,
        "label": "tropical monsoon",
    },
    "tropical_equatorial": {
        "monthly_high_c": [30, 31, 32, 32, 32, 31, 31, 31, 31, 31, 31, 30],
        "monthly_low_c": [24, 24, 25, 25, 25, 25, 25, 25, 25, 24, 24, 24],
        "rain_chance": [55, 45, 50, 55, 55, 50, 50, 50, 55, 60, 65, 65],
        "humidity": 82,
        "label": "tropical equatorial",
    },
    "desert": {
        "monthly_high_c": [24, 26, 29, 34, 39, 41, 42, 42, 39, 35, 30, 26],
        "monthly_low_c": [14, 15, 18, 21, 26, 28, 30, 30, 27, 23, 19, 16],
        "rain_chance": [12, 10, 8, 4, 2, 0, 0, 0, 0, 2, 6, 10],
        "humidity": 45,
        "label": "hot desert",
    },
    "temperate_maritime": {
        "monthly_high_c": [8, 9, 12, 15, 18, 21, 23, 23, 20, 16, 11, 9],
        "monthly_low_c": [3, 3, 5, 7, 10, 13, 15, 15, 13, 10, 6, 4],
        "rain_chance": [50, 45, 42, 40, 38, 36, 35, 38, 40, 48, 52, 53],
        "humidity": 78,
        "label": "temperate maritime",
    },
    "temperate_continental": {
        "monthly_high_c": [2, 4, 9, 15, 20, 24, 26, 25, 20, 14, 7, 3],
        "monthly_low_c": [-4, -3, 1, 5, 10, 14, 16, 15, 11, 6, 1, -2],
        "rain_chance": [35, 32, 33, 35, 40, 42, 40, 38, 35, 34, 38, 38],
        "humidity": 70,
        "label": "temperate continental",
    },
    "mediterranean": {
        "monthly_high_c": [13, 14, 17, 20, 24, 29, 32, 32, 28, 23, 17, 14],
        "monthly_low_c": [4, 5, 7, 10, 14, 18, 20, 20, 17, 13, 8, 5],
        "rain_chance": [45, 42, 38, 35, 25, 12, 5, 6, 18, 38, 48, 50],
        "humidity": 62,
        "label": "mediterranean",
    },
    "subtropical_humid": {
        "monthly_high_c": [10, 12, 16, 21, 25, 28, 31, 32, 29, 24, 18, 12],
        "monthly_low_c": [2, 3, 6, 11, 16, 20, 24, 25, 21, 15, 9, 4],
        "rain_chance": [30, 35, 40, 42, 45, 55, 50, 45, 45, 38, 32, 30],
        "humidity": 72,
        "label": "humid subtropical",
    },
    "oceanic_southern": {
        "monthly_high_c": [26, 26, 25, 22, 19, 17, 16, 18, 20, 22, 24, 25],
        "monthly_low_c": [19, 19, 18, 15, 12, 9, 8, 9, 11, 14, 16, 18],
        "rain_chance": [32, 35, 38, 38, 38, 40, 35, 32, 32, 32, 33, 33],
        "humidity": 66,
        "label": "oceanic",
    },
}

CITY_ZONE: dict[str, str] = {
    "dhaka": "tropical_monsoon",
    "chittagong": "tropical_monsoon",
    "kolkata": "tropical_monsoon",
    "delhi": "tropical_monsoon",
    "new delhi": "tropical_monsoon",
    "mumbai": "tropical_monsoon",
    "chennai": "tropical_monsoon",
    "bengaluru": "tropical_monsoon",
    "bangalore": "tropical_monsoon",
    "goa": "tropical_monsoon",
    "kathmandu": "subtropical_humid",
    "colombo": "tropical_equatorial",
    "male": "tropical_equatorial",
    "bangkok": "tropical_monsoon",
    "phuket": "tropical_equatorial",
    "singapore": "tropical_equatorial",
    "kuala lumpur": "tropical_equatorial",
    "bali": "tropical_equatorial",
    "jakarta": "tropical_equatorial",
    "hanoi": "subtropical_humid",
    "tokyo": "subtropical_humid",
    "kyoto": "subtropical_humid",
    "osaka": "subtropical_humid",
    "seoul": "temperate_continental",
    "hong kong": "subtropical_humid",
    "dubai": "desert",
    "abu dhabi": "desert",
    "doha": "desert",
    "cairo": "desert",
    "istanbul": "mediterranean",
    "rome": "mediterranean",
    "barcelona": "mediterranean",
    "london": "temperate_maritime",
    "paris": "temperate_maritime",
    "amsterdam": "temperate_maritime",
    "berlin": "temperate_continental",
    "zurich": "temperate_continental",
    "new york": "temperate_continental",
    "toronto": "temperate_continental",
    "san francisco": "mediterranean",
    "los angeles": "mediterranean",
    "sydney": "oceanic_southern",
    "melbourne": "oceanic_southern",
    "cape town": "mediterranean",
    "nairobi": "subtropical_humid",
}

DEFAULT_ZONE = "temperate_maritime"


def zone_for(location: str) -> str:
    key = (location or "").strip().lower()
    if key in CITY_ZONE:
        return CITY_ZONE[key]
    for city, zone in CITY_ZONE.items():
        if key and (key in city or city in key):
            return zone
    return DEFAULT_ZONE


def _condition(rain_chance: float, high: float) -> str:
    if rain_chance >= 65:
        return "frequent rain showers"
    if rain_chance >= 40:
        return "scattered showers"
    if high >= 35:
        return "hot and sunny"
    if high <= 5:
        return "cold, mostly cloudy"
    if rain_chance >= 25:
        return "partly cloudy"
    return "mostly sunny"


def _climate_day(zone_key: str, day: date) -> dict[str, Any]:
    zone = CLIMATE_ZONES[zone_key]
    index = day.month - 1
    high = float(zone["monthly_high_c"][index])
    low = float(zone["monthly_low_c"][index])
    rain = float(zone["rain_chance"][index])
    # Small deterministic day-to-day variation so a forecast is not a flat line.
    wobble = ((day.toordinal() * 37) % 7) - 3
    return {
        "date": day.isoformat(),
        "condition": _condition(rain, high),
        "temp_min_c": round(low + wobble * 0.4, 1),
        "temp_max_c": round(high + wobble * 0.5, 1),
        "humidity_pct": float(zone["humidity"]),
        "precipitation_chance_pct": max(0.0, min(100.0, round(rain + wobble * 2, 1))),
    }


def packing_advice(days: list[dict[str, Any]], zone_key: str) -> tuple[list[str], list[Any]]:
    """Return (english_text, phrase_codes) for packing guidance."""
    if not days:
        return [], []
    max_temp = max(day["temp_max_c"] for day in days)
    min_temp = min(day["temp_min_c"] for day in days)
    wettest = max(day["precipitation_chance_pct"] for day in days)
    codes: list[Any] = []

    if max_temp >= 32:
        codes.append("packing.hot")
    if max_temp >= 38:
        codes.append("packing.very_hot")
    if min_temp <= 8:
        codes.append("packing.cool")
    if min_temp <= 0:
        codes.append("packing.freezing")
    if wettest >= 50:
        codes.append("packing.rain")
    if CLIMATE_ZONES[zone_key]["humidity"] >= 75:
        codes.append("packing.humid")
    if not codes:
        codes.append("packing.layers")

    return translate_all(codes, "en"), codes


def travel_suggestions(days: list[dict[str, Any]]) -> tuple[list[str], list[Any]]:
    """Return (english_text, phrase_codes) for weather-driven advice."""
    if not days:
        return [], []
    wet_days = [day for day in days if day["precipitation_chance_pct"] >= 55]
    hot_days = [day for day in days if day["temp_max_c"] >= 35]
    codes: list[Any] = []
    if wet_days:
        codes.append(["weather.indoor_ready", {"dates": ", ".join(d["date"] for d in wet_days[:3])}])
    if hot_days:
        codes.append("weather.morning_walks")
    if not wet_days and not hot_days:
        codes.append("weather.outdoor_ok")
    return translate_all(codes, "en"), codes


# --- Live provider --------------------------------------------------------
async def _openweather_current(location: str, api_key: str, timeout: int) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{OPENWEATHER_BASE}/weather",
            params={"q": location, "appid": api_key, "units": "metric"},
        )
        response.raise_for_status()
        return response.json()


async def _openweather_forecast(location: str, api_key: str, timeout: int) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{OPENWEATHER_BASE}/forecast",
            params={"q": location, "appid": api_key, "units": "metric"},
        )
        response.raise_for_status()
        return response.json()


def _aggregate_openweather(payload: dict[str, Any], days: int) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for entry in payload.get("list", []):
        day_key = (entry.get("dt_txt") or "")[:10]
        if not day_key:
            continue
        main = entry.get("main") or {}
        weather = (entry.get("weather") or [{}])[0]
        bucket = buckets.setdefault(
            day_key,
            {
                "date": day_key,
                "condition": weather.get("description"),
                "temp_min_c": main.get("temp_min"),
                "temp_max_c": main.get("temp_max"),
                "humidity_pct": main.get("humidity"),
                "precipitation_chance_pct": round(float(entry.get("pop", 0)) * 100, 1),
            },
        )
        if main.get("temp_min") is not None:
            bucket["temp_min_c"] = min(bucket["temp_min_c"], main["temp_min"])
        if main.get("temp_max") is not None:
            bucket["temp_max_c"] = max(bucket["temp_max_c"], main["temp_max"])
        bucket["precipitation_chance_pct"] = max(
            bucket["precipitation_chance_pct"], round(float(entry.get("pop", 0)) * 100, 1)
        )
    return list(buckets.values())[:days]


# --- Tool implementations -------------------------------------------------
async def get_current_weather(*, location: str) -> dict[str, Any]:
    """Tool implementation for ``get_current_weather``."""
    settings = get_settings()
    zone_key = zone_for(location)

    if settings.openweather_api_key:
        try:
            payload = await _openweather_current(
                location, settings.openweather_api_key, settings.provider_timeout_seconds
            )
            main = payload.get("main") or {}
            weather = (payload.get("weather") or [{}])[0]
            wind = payload.get("wind") or {}
            return {
                "location": payload.get("name") or location,
                "current": {
                    "temperature_c": main.get("temp"),
                    "feels_like_c": main.get("feels_like"),
                    "condition": weather.get("description"),
                    "humidity_pct": main.get("humidity"),
                    "wind_kph": round(float(wind.get("speed", 0)) * 3.6, 1),
                },
                "source": SOURCE_LIVE,
                "provider": "openweather",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "notes": [],
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("openweather current failed", extra={"error": str(exc)})

    today = _climate_day(zone_key, date.today())
    return {
        "location": location,
        "current": {
            "temperature_c": round((today["temp_max_c"] + today["temp_min_c"]) / 2, 1),
            "feels_like_c": round((today["temp_max_c"] + today["temp_min_c"]) / 2 + 1.5, 1),
            "condition": today["condition"],
            "humidity_pct": today["humidity_pct"],
            "wind_kph": 12.0,
        },
        "source": SOURCE_ESTIMATE,
        "provider": "journeymesh_climate_normals",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "notes": [
            f"Climate-normal projection for a {CLIMATE_ZONES[zone_key]['label']} destination; "
            "not a live observation."
        ],
    }


async def get_weather_forecast(*, location: str, days: int = 5) -> dict[str, Any]:
    """Tool implementation for ``get_weather_forecast``."""
    settings = get_settings()
    days = max(1, min(int(days), 14))
    zone_key = zone_for(location)
    notes: list[str] = []
    forecast: list[dict[str, Any]] = []
    source = SOURCE_ESTIMATE
    provider = "journeymesh_climate_normals"

    if settings.openweather_api_key:
        try:
            payload = await _openweather_forecast(
                location, settings.openweather_api_key, settings.provider_timeout_seconds
            )
            forecast = _aggregate_openweather(payload, days)
            if forecast:
                source = SOURCE_LIVE
                provider = "openweather"
                if len(forecast) < days:
                    notes.append(
                        f"Live forecast covers {len(forecast)} of {days} days; "
                        "later days use climate normals."
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("openweather forecast failed", extra={"error": str(exc)})
            notes.append("The live weather provider was unavailable.")

    if len(forecast) < days:
        start = date.today() + timedelta(days=len(forecast))
        for offset in range(days - len(forecast)):
            forecast.append(_climate_day(zone_key, start + timedelta(days=offset)))
        if source != SOURCE_LIVE:
            notes.append(
                f"Climate-normal projection for a {CLIMATE_ZONES[zone_key]['label']} "
                "destination; not a live forecast."
            )

    packing_text, packing_codes = packing_advice(forecast, zone_key)
    suggestion_text, suggestion_codes = travel_suggestions(forecast)

    return {
        "location": location,
        "forecast": forecast,
        "packing_recommendations": packing_text,
        "travel_suggestions": suggestion_text,
        "packing_codes": packing_codes,
        "suggestion_codes": suggestion_codes,
        "source": source,
        "provider": provider,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
    }


TOOLS = {
    "get_current_weather": get_current_weather,
    "get_weather_forecast": get_weather_forecast,
}


# --- Standalone stdio MCP server -----------------------------------------
def build_server():  # pragma: no cover - exercised only when run as a server
    """Build the FastMCP server exposing the weather tools."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("journeymesh-weather")

    @server.tool()
    async def current_weather(location: str) -> dict[str, Any]:
        """Current conditions for a destination."""
        return await get_current_weather(location=location)

    @server.tool()
    async def weather_forecast(location: str, days: int = 5) -> dict[str, Any]:
        """Multi-day forecast, packing advice and travel suggestions."""
        return await get_weather_forecast(location=location, days=days)

    return server


def main() -> None:  # pragma: no cover
    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()


async def _demo() -> None:  # pragma: no cover - convenience for manual checks
    print(await get_weather_forecast(location="Singapore", days=3))


if __name__ == "__demo__":  # pragma: no cover
    asyncio.run(_demo())
