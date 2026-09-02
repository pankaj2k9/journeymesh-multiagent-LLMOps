"""Itinerary Agent.

Builds a realistic day-by-day plan from everything the other agents put in
the state: the constraints, the flights, the stay, the forecast and the
budget. Structure is produced deterministically - pacing, travel time, rest
and weather fit are rules, not guesses - and the language model, when one is
configured, is used only to make the descriptions specific to the place.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import ITINERARY_AGENT
from app.core.i18n import translate_all
from app.graph.state import TravelState
from app.schemas.itinerary import Activity, DaySlot, ItineraryDay, ItineraryPlan

# Activity templates per interest. ``indoor`` drives the wet-weather swap and
# ``cost`` is a planning estimate per person in USD.
_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "food": [
        {"title": "Local breakfast crawl", "indoor": False, "cost": 12, "minutes": 90},
        {"title": "Street food walking route", "indoor": False, "cost": 18, "minutes": 120},
        {"title": "Cooking class with a local host", "indoor": True, "cost": 45, "minutes": 180},
        {"title": "Night market dinner", "indoor": False, "cost": 22, "minutes": 120},
    ],
    "nature": [
        {"title": "Botanical gardens walk", "indoor": False, "cost": 8, "minutes": 120},
        {"title": "Coastal or riverside trail", "indoor": False, "cost": 0, "minutes": 150},
        {"title": "Half-day nature reserve trip", "indoor": False, "cost": 35, "minutes": 240},
        {"title": "Sunset viewpoint", "indoor": False, "cost": 0, "minutes": 90},
    ],
    "history": [
        {"title": "Old quarter guided walk", "indoor": False, "cost": 20, "minutes": 150},
        {"title": "National museum", "indoor": True, "cost": 15, "minutes": 120},
        {"title": "Heritage site visit", "indoor": False, "cost": 18, "minutes": 150},
    ],
    "culture": [
        {"title": "Contemporary art gallery", "indoor": True, "cost": 14, "minutes": 120},
        {"title": "Neighbourhood arts district", "indoor": False, "cost": 0, "minutes": 120},
        {"title": "Live music or theatre evening", "indoor": True, "cost": 30, "minutes": 150},
    ],
    "shopping": [
        {"title": "Covered market browse", "indoor": True, "cost": 0, "minutes": 90},
        {"title": "Design and craft shopping street", "indoor": False, "cost": 0, "minutes": 120},
        {"title": "Shopping mall break", "indoor": True, "cost": 0, "minutes": 120},
    ],
    "beaches": [
        {"title": "Beach morning", "indoor": False, "cost": 0, "minutes": 180},
        {"title": "Boat trip along the coast", "indoor": False, "cost": 40, "minutes": 240},
        {"title": "Seafront promenade at sunset", "indoor": False, "cost": 0, "minutes": 90},
    ],
    "nightlife": [
        {"title": "Rooftop bar with a skyline view", "indoor": False, "cost": 25, "minutes": 120},
        {"title": "Live music venue", "indoor": True, "cost": 22, "minutes": 150},
    ],
    "photography": [
        {"title": "Sunrise photo walk", "indoor": False, "cost": 0, "minutes": 120},
        {"title": "Viewpoint and skyline shoot", "indoor": False, "cost": 10, "minutes": 120},
        {"title": "Architecture photo route", "indoor": False, "cost": 0, "minutes": 120},
    ],
    "technology": [
        {"title": "Science and technology museum", "indoor": True, "cost": 18, "minutes": 150},
        {"title": "Innovation district walk", "indoor": False, "cost": 0, "minutes": 120},
    ],
    "family_activities": [
        {"title": "City aquarium", "indoor": True, "cost": 28, "minutes": 150},
        {"title": "Zoo or wildlife park", "indoor": False, "cost": 25, "minutes": 210},
        {"title": "Playground and picnic in the park", "indoor": False, "cost": 5, "minutes": 120},
        {"title": "Interactive children's museum", "indoor": True, "cost": 20, "minutes": 120},
    ],
}

_DEFAULT_INTERESTS = ("culture", "food", "nature")

_INDOOR_FALLBACKS = [
    {"title": "City museum visit", "indoor": True, "cost": 15, "minutes": 120},
    {"title": "Covered market and cafe stop", "indoor": True, "cost": 12, "minutes": 90},
    {"title": "Aquarium or science centre", "indoor": True, "cost": 24, "minutes": 150},
]

# Activities per day by travel style.
_PACING = {
    "relaxed": ("relaxed", 2),
    "family": ("relaxed", 2),
    "luxury": ("balanced", 3),
    "comfort": ("balanced", 3),
    "business": ("balanced", 2),
    "budget": ("balanced", 3),
    "adventure": ("packed", 4),
}

_SLOT_ORDER = ("morning", "afternoon", "evening")


class ItineraryAgent(BaseAgent):
    name = ITINERARY_AGENT

    async def execute(self, state: TravelState) -> None:
        constraints = self.constraints(state)
        destination = constraints.get("destination") or "your destination"
        days_count = self._day_count(constraints)
        pacing, per_day = _PACING.get(constraints.get("travel_style") or "comfort", ("balanced", 3))

        interests = list(constraints.get("interests") or [])
        if int(constraints.get("travelers") or 1) > 2 and "family_activities" not in interests:
            interests.append("family_activities")
        if not interests:
            interests = list(_DEFAULT_INTERESTS)

        pool = self._activity_pool(interests, destination)
        forecast = self._forecast_by_day(state, days_count)
        start_date = self._start_date(constraints)

        plan = ItineraryPlan(
            destination=destination,
            total_days=days_count,
            pacing=pacing,  # type: ignore[arg-type]
            currency=(constraints.get("currency") or "USD").upper(),
        )

        cursor = 0
        for index in range(days_count):
            day_date = start_date + timedelta(days=index) if start_date else None
            weather = forecast[index] if index < len(forecast) else None
            wet = bool(weather and (weather.get("precipitation_chance_pct") or 0) >= 55)
            hot = bool(weather and (weather.get("temp_max_c") or 0) >= 35)

            first_day = index == 0
            last_day = index == days_count - 1 and days_count > 1
            budget_for_day = per_day - (1 if (first_day or last_day) else 0)
            budget_for_day = max(budget_for_day, 1)

            day = ItineraryDay(
                day=index + 1,
                date=day_date.isoformat() if day_date else None,
                title=self._day_title(index, days_count, destination),
                weather_note=self._weather_note(weather),
            )

            slots: list[DaySlot] = []
            for slot_index, slot_name in enumerate(_SLOT_ORDER):
                activities: list[Activity] = []
                if first_day and slot_name == "morning":
                    activities.append(self._arrival_activity(state, destination))
                elif last_day and slot_name == "evening":
                    activities.append(self._departure_activity(state, destination))
                elif slot_index < budget_for_day:
                    template, cursor = self._pick(pool, cursor, prefer_indoor=wet)
                    if hot and slot_name == "afternoon" and not template["indoor"]:
                        template, cursor = self._pick(pool, cursor, prefer_indoor=True)
                    activities.append(self._to_activity(template, destination, constraints))

                if not activities:
                    continue

                slots.append(
                    DaySlot(
                        slot=slot_name,  # type: ignore[arg-type]
                        activities=activities,
                        travel_time_minutes=20 if slot_index else 15,
                        notes=self._slot_note(slot_name, wet, hot),
                    )
                )

            day.slots = slots
            day.estimated_day_cost = round(
                sum(
                    float(activity.estimated_cost or 0)
                    for slot in slots
                    for activity in slot.activities
                ),
                2,
            )
            day.summary = self._day_summary(day, destination)
            if pacing == "relaxed" or index in (0, days_count - 1):
                day.rest_note = "A slower day with time to rest between activities."
            plan.days.append(day)

        travelers = max(int(constraints.get("travelers") or 1), 1)
        plan.estimated_activity_cost = round(
            sum(day.estimated_day_cost or 0 for day in plan.days) * travelers, 2
        )
        plan.travel_tips, plan.travel_tip_codes = self._tips(state, constraints)
        plan.notes = self._notes(state, constraints)

        plan = await self._enrich(plan, state, constraints)
        state["itinerary_plan"] = plan.model_dump(mode="json")
        self.track_llm(state)
        self.note(
            state,
            f"{days_count}-day {pacing} itinerary drafted with "
            f"{sum(len(slot.activities) for day in plan.days for slot in day.slots)} activities.",
        )

    # ---- structure -------------------------------------------------------
    def _day_count(self, constraints: dict[str, Any]) -> int:
        days = constraints.get("trip_days")
        if days:
            return max(1, min(int(days), 30))
        nights = constraints.get("nights")
        if nights:
            return max(1, min(int(nights) + 1, 30))
        return 3

    def _start_date(self, constraints: dict[str, Any]) -> date | None:
        value = constraints.get("departure_date")
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    def _activity_pool(self, interests: list[str], destination: str) -> list[dict[str, Any]]:
        pool: list[dict[str, Any]] = []
        # Interleave interests so no single interest dominates the first days.
        per_interest = [list(_TEMPLATES.get(interest, [])) for interest in interests]
        depth = max((len(items) for items in per_interest), default=0)
        for level in range(depth):
            for items in per_interest:
                if level < len(items):
                    pool.append(dict(items[level], interest=interests[per_interest.index(items)]))
        if not pool:
            pool = [dict(item, interest="culture") for item in _INDOOR_FALLBACKS]
        return pool

    def _pick(
        self, pool: list[dict[str, Any]], cursor: int, *, prefer_indoor: bool
    ) -> tuple[dict[str, Any], int]:
        size = len(pool)
        if prefer_indoor:
            for offset in range(size):
                candidate = pool[(cursor + offset) % size]
                if candidate.get("indoor"):
                    return candidate, cursor + offset + 1
            fallback = _INDOOR_FALLBACKS[cursor % len(_INDOOR_FALLBACKS)]
            return dict(fallback, interest="indoor"), cursor + 1
        return pool[cursor % size], cursor + 1

    def _to_activity(
        self, template: dict[str, Any], destination: str, constraints: dict[str, Any]
    ) -> Activity:
        family = int(constraints.get("travelers") or 1) > 2 or constraints.get("travel_style") == "family"
        return Activity(
            title=template["title"],
            description=f"{template['title']} in {destination}.",
            location=destination,
            duration_minutes=int(template.get("minutes") or 120),
            estimated_cost=float(template.get("cost") or 0),
            currency=(constraints.get("currency") or "USD").upper(),
            indoor=bool(template.get("indoor")),
            family_friendly=not (template.get("interest") == "nightlife" and family),
            tags=[template.get("interest", "general")],
        )

    def _arrival_activity(self, state: TravelState, destination: str) -> Activity:
        hotels = state.get("hotel_results") or {}
        options = hotels.get("options") or []
        stay = options[0]["name"] if options else "your accommodation"
        return Activity(
            title="Arrival and check-in",
            description=f"Transfer into {destination} and settle in at {stay}.",
            location=destination,
            duration_minutes=180,
            estimated_cost=0.0,
            indoor=True,
            tags=["logistics"],
        )

    def _departure_activity(self, state: TravelState, destination: str) -> Activity:
        return Activity(
            title="Check-out and departure",
            description=f"Final stroll in {destination}, then transfer to the airport.",
            location=destination,
            duration_minutes=180,
            estimated_cost=0.0,
            indoor=True,
            tags=["logistics"],
        )

    # ---- context ---------------------------------------------------------
    def _forecast_by_day(self, state: TravelState, days: int) -> list[dict[str, Any]]:
        weather = state.get("weather_info") or {}
        forecast = list(weather.get("forecast") or [])
        return forecast[:days]

    def _weather_note(self, weather: dict[str, Any] | None) -> str | None:
        if not weather:
            return None
        return (
            f"{weather.get('condition', 'mixed conditions')}, "
            f"{weather.get('temp_min_c')}-{weather.get('temp_max_c')}C, "
            f"{weather.get('precipitation_chance_pct')}% chance of rain"
        )

    def _slot_note(self, slot: str, wet: bool, hot: bool) -> str | None:
        if wet and slot in ("morning", "afternoon"):
            return "Rain is likely - an indoor option is scheduled."
        if hot and slot == "afternoon":
            return "Kept indoors during the hottest hours."
        if slot == "evening":
            return "Keep the evening flexible."
        return None

    def _day_title(self, index: int, total: int, destination: str) -> str:
        if index == 0:
            return f"Arrival in {destination}"
        if index == total - 1 and total > 1:
            return f"Last day in {destination}"
        return f"Day {index + 1} in {destination}"

    def _day_summary(self, day: ItineraryDay, destination: str) -> str:
        titles = [
            activity.title
            for slot in day.slots
            for activity in slot.activities
        ]
        if not titles:
            return f"A free day in {destination}."
        return " then ".join(titles[:3]) + "."

    def _tips(self, state: TravelState, constraints: dict[str, Any]) -> tuple[list[str], list[Any]]:
        """Return (english_text, phrase_codes) for the trip-level tips."""
        weather = state.get("weather_info") or {}
        codes: list[Any] = []
        codes.extend((weather.get("packing_codes") or [])[:3])
        codes.extend((weather.get("suggestion_codes") or [])[:2])

        if int(constraints.get("travelers") or 1) > 2:
            codes.append("tip.family_rooms")
        if constraints.get("special_requirements"):
            codes.append("tip.special_requirements")
        codes.append("tip.transit_card")

        deduped: list[Any] = []
        seen: set[str] = set()
        for code in codes:
            key = code if isinstance(code, str) else str(code)
            if key not in seen:
                seen.add(key)
                deduped.append(code)
        deduped = deduped[:6]
        return translate_all(deduped, "en"), deduped

    def _notes(self, state: TravelState, constraints: dict[str, Any]) -> list[str]:
        notes: list[str] = []
        if not (state.get("weather_info") or {}).get("forecast"):
            notes.append("No forecast was available, so activities are not weather-adjusted.")
        if not (state.get("hotel_results") or {}).get("options"):
            notes.append("No accommodation was selected, so check-in timings are indicative.")
        return notes

    # ---- optional model enrichment --------------------------------------
    async def _enrich(
        self, plan: ItineraryPlan, state: TravelState, constraints: dict[str, Any]
    ) -> ItineraryPlan:
        """Ask the model to make titles and descriptions specific to the city."""
        if not self.llm.available or not plan.days:
            return plan

        outline = [
            {
                "day": day.day,
                "activities": [
                    activity.title for slot in day.slots for activity in slot.activities
                ],
            }
            for day in plan.days
        ]
        system = (
            "You localise a travel itinerary. For each activity you are given a generic "
            "title. Replace it with a specific, real, well-known option in the named city "
            "when you are confident one exists; otherwise keep the generic title unchanged. "
            "Never invent opening hours, prices or bookings. Return JSON: "
            '{"days": [{"day": 1, "activities": ["...", "..."]}]} with exactly the same '
            "number of activities per day."
        )
        user = (
            f"City: {plan.destination}\n"
            f"Traveller interests: {constraints.get('interests')}\n"
            f"Travel style: {constraints.get('travel_style')}\n"
            f"Outline: {outline}"
        )
        payload = await self.llm.complete_json(
            system=system, user=user, purpose="itinerary_localisation"
        )
        if not payload:
            return plan

        by_day = {
            int(entry.get("day", 0)): entry.get("activities") or []
            for entry in payload.get("days", [])
            if isinstance(entry, dict)
        }
        for day in plan.days:
            replacements = by_day.get(day.day)
            if not replacements:
                continue
            flat = [activity for slot in day.slots for activity in slot.activities]
            if len(replacements) != len(flat):
                continue
            for activity, title in zip(flat, replacements):
                if isinstance(title, str) and 3 <= len(title) <= 120:
                    activity.title = title.strip()
                    activity.description = f"{title.strip()} in {plan.destination}."
            day.summary = self._day_summary(day, plan.destination or "")
        return plan
