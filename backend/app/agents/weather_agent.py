"""Weather Agent.

Calls the custom JourneyMesh weather MCP for current conditions and a forecast
covering the travel window, then turns that into packing advice and activity
guidance the Itinerary Agent can act on.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import SOURCE_UNAVAILABLE, WEATHER_AGENT
from app.core.i18n import translate_all
from app.graph.state import TravelState
from app.schemas.weather import WeatherInfo


class WeatherAgent(BaseAgent):
    name = WEATHER_AGENT
    provider_kind = "weather"

    async def execute(self, state: TravelState) -> None:
        constraints = self.constraints(state)
        destination = constraints.get("destination")

        if not destination:
            state["weather_info"] = WeatherInfo(
                source=SOURCE_UNAVAILABLE,
                notes=["No destination was provided, so no forecast could be retrieved."],
            ).model_dump(mode="json")
            self.note(state, "Skipped: the journey has no destination yet.")
            return

        days = self._forecast_days(constraints)

        current = await self.call_tool(
            state, "get_current_weather", {"location": destination}, provider="weather_mcp"
        )
        forecast = await self.call_tool(
            state,
            "get_weather_forecast",
            {"location": destination, "days": days},
            provider="weather_mcp",
        )

        if not forecast.ok and not current.ok:
            state["weather_info"] = WeatherInfo(
                location=destination,
                source=SOURCE_UNAVAILABLE,
                notes=["The weather service was unavailable for this journey."],
            ).model_dump(mode="json")
            return

        payload: dict[str, Any] = dict(forecast.data) if forecast.ok else {"location": destination}
        if current.ok:
            payload["current"] = current.data.get("current")
            payload.setdefault("source", current.data.get("source"))
            payload.setdefault("provider", current.data.get("provider"))

        payload.setdefault("location", destination)
        payload["retrieved_at"] = datetime.now(timezone.utc).isoformat()

        weather = WeatherInfo.model_validate(payload)
        weather.travel_suggestions, weather.suggestion_codes = self._suggestions(
            weather, constraints
        )
        state["weather_info"] = weather.model_dump(mode="json")

        if weather.forecast:
            wet = sum(
                1 for day in weather.forecast if (day.precipitation_chance_pct or 0) >= 55
            )
            self.note(
                state,
                f"{len(weather.forecast)}-day outlook retrieved ({weather.source}); "
                f"{wet} day(s) with a high chance of rain.",
            )
        else:
            self.note(state, "Current conditions retrieved; no multi-day outlook available.")

    def _forecast_days(self, constraints: dict[str, Any]) -> int:
        trip_days = constraints.get("trip_days")
        if trip_days:
            return max(1, min(int(trip_days), 14))

        departure = constraints.get("departure_date")
        returning = constraints.get("return_date")
        if departure and returning:
            try:
                start = date.fromisoformat(str(departure))
                end = date.fromisoformat(str(returning))
                return max(1, min((end - start).days + 1, 14))
            except ValueError:
                pass
        return 5

    def _suggestions(
        self, weather: WeatherInfo, constraints: dict[str, Any]
    ) -> tuple[list[str], list[Any]]:
        """Extend the provider's advice with party-specific guidance."""
        codes: list[Any] = list(weather.suggestion_codes)
        interests = set(constraints.get("interests") or [])

        wet_days = [
            day.date for day in weather.forecast if (day.precipitation_chance_pct or 0) >= 55
        ]
        hot_days = [day.date for day in weather.forecast if (day.temp_max_c or 0) >= 35]

        if wet_days and ("beaches" in interests or "nature" in interests):
            codes.append(["weather.indoor_ready", {"dates": ", ".join(wet_days[:2])}])
        if hot_days and int(constraints.get("travelers") or 1) > 2:
            codes.append("weather.kids_midday")
        if not weather.forecast:
            codes.append("weather.check_again")

        deduped: list[Any] = []
        seen: set[str] = set()
        for code in codes:
            key = code if isinstance(code, str) else str(code)
            if key not in seen:
                seen.add(key)
                deduped.append(code)
        return translate_all(deduped, "en"), deduped
