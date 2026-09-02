"""Hotel Agent.

Researches accommodation for the destination and ranks candidates against the
traveller's budget, style, party size and stated interests. Nightly rates keep
the provenance the provider gave them.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import HOTEL_AGENT, SOURCE_UNAVAILABLE
from app.graph.state import TravelState
from app.schemas.hotel import HotelOption, HotelResults

# Share of the total budget that is reasonable to spend on accommodation.
_ACCOMMODATION_SHARE = {
    "budget": 0.30,
    "comfort": 0.35,
    "luxury": 0.45,
    "adventure": 0.25,
    "family": 0.38,
    "business": 0.40,
    "relaxed": 0.38,
}


class HotelAgent(BaseAgent):
    name = HOTEL_AGENT
    provider_kind = "hotels"

    async def execute(self, state: TravelState) -> None:
        constraints = self.constraints(state)
        destination = constraints.get("destination")

        if not destination:
            state["hotel_results"] = HotelResults(
                source=SOURCE_UNAVAILABLE,
                notes=["No destination was provided, so no stays could be researched."],
            ).model_dump(mode="json")
            self.note(state, "Skipped: the journey has no destination yet.")
            return

        nights = int(constraints.get("nights") or 0) or 1
        travelers = max(int(constraints.get("travelers") or 1), 1)
        ceiling = self._nightly_ceiling(constraints, nights)

        arguments: dict[str, Any] = {
            "destination": destination,
            "travelers": travelers,
        }
        if constraints.get("travel_style"):
            arguments["travel_style"] = constraints["travel_style"]
        if ceiling:
            arguments["max_price_per_night"] = round(ceiling, 2)

        result = await self.call_tool(state, "search_hotels", arguments, provider="search_mcp")
        if not result.ok:
            state["hotel_results"] = HotelResults(
                destination=destination,
                nights=nights,
                source=SOURCE_UNAVAILABLE,
                notes=["Accommodation research was unavailable for this journey."],
            ).model_dump(mode="json")
            return

        payload = dict(result.data)
        payload["nights"] = nights
        payload["price_ceiling_per_night"] = round(ceiling, 2) if ceiling else None

        hotels = HotelResults.model_validate(payload)
        hotels.options = self._rank(hotels.options, constraints, ceiling)
        hotels.recommended_index = 0
        if hotels.options:
            hotels.options[0].why_recommended = self._why(hotels.options[0], constraints, ceiling)

        state["hotel_results"] = hotels.model_dump(mode="json")

        if hotels.options:
            top = hotels.options[0]
            rate = f"{top.price_per_night:.0f} {top.currency or ''}".strip() if top.price_per_night else "rate on request"
            self.note(
                state,
                f"{len(hotels.options)} stay(s) shortlisted; recommending {top.name} at {rate} per night.",
            )
        else:
            self.note(state, "No accommodation candidate matched the constraints.")

    # ---- ranking ---------------------------------------------------------
    def _nightly_ceiling(self, constraints: dict[str, Any], nights: int) -> float | None:
        explicit = constraints.get("max_hotel_price_per_night")
        if explicit:
            return float(explicit)

        budget = constraints.get("budget")
        if not budget or nights <= 0:
            return None
        share = _ACCOMMODATION_SHARE.get(constraints.get("travel_style") or "comfort", 0.35)
        return max(float(budget) * share / nights, 15.0)

    def _rank(
        self,
        options: list[HotelOption],
        constraints: dict[str, Any],
        ceiling: float | None,
    ) -> list[HotelOption]:
        travelers = int(constraints.get("travelers") or 1)
        style = constraints.get("travel_style")
        interests = set(constraints.get("interests") or [])
        wants_family = travelers > 2 or style == "family" or "family_activities" in interests

        def score(option: HotelOption) -> float:
            value = 0.0
            if option.price_per_night is not None and ceiling:
                if option.price_per_night <= ceiling:
                    value += 3.0 + (1 - option.price_per_night / ceiling)
                else:
                    value -= 2.0 * (option.price_per_night / ceiling - 1)
            elif option.price_per_night is None:
                value -= 0.5
            if option.rating:
                value += float(option.rating) / 2
            if wants_family and option.family_friendly:
                value += 1.5
            if option.distance_to_centre_km is not None:
                value += max(0.0, 1.5 - option.distance_to_centre_km / 4)
            if style == "luxury" and (option.rating or 0) >= 4.4:
                value += 1.0
            if style == "budget" and option.price_per_night:
                value += 1.0 if option.price_per_night <= (ceiling or 1e9) * 0.7 else 0.0
            if "food" in interests and any("breakfast" in a for a in option.amenities):
                value += 0.5
            return value

        return sorted(options, key=score, reverse=True)

    def _why(
        self, option: HotelOption, constraints: dict[str, Any], ceiling: float | None
    ) -> str:
        parts: list[str] = []
        if option.price_per_night and ceiling:
            parts.append(
                f"fits the {ceiling:.0f} per night ceiling at {option.price_per_night:.0f}"
            )
        elif option.price_per_night:
            parts.append(f"priced at about {option.price_per_night:.0f} per night")
        if option.family_friendly and int(constraints.get("travelers") or 1) > 2:
            parts.append("has family rooms for the whole party")
        if option.area:
            parts.append(f"sits in the {option.area.lower()}")
        if option.rating:
            parts.append(f"rated {option.rating}")
        return "Recommended because it " + ", ".join(parts) + "." if parts else "Best overall match."
