"""Budget Agent.

Turns the agents' output into a cost picture the traveller can act on. It
keeps provider-confirmed prices and JourneyMesh estimates in separate
buckets, so an estimate is never presented as a live price, and it can be
re-run on its own after a change without touching any other agent.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import (
    BUDGET_AGENT,
    BUDGET_INSUFFICIENT,
    BUDGET_NEAR_LIMIT,
    BUDGET_OVER,
    BUDGET_WITHIN,
    NEAR_LIMIT_THRESHOLD,
    SOURCE_ESTIMATE,
    SOURCE_LIVE,
    SOURCE_SEARCH_DERIVED,
)
from app.graph.state import TravelState
from app.schemas.budget import BudgetAnalysis, BudgetBreakdown, BudgetLine

# Daily per-person planning allowances in USD by travel style.
_DAILY_ALLOWANCE = {
    "budget": {"food": 18.0, "transport": 7.0, "activities": 10.0, "misc": 5.0},
    "comfort": {"food": 42.0, "transport": 16.0, "activities": 28.0, "misc": 12.0},
    "luxury": {"food": 120.0, "transport": 55.0, "activities": 90.0, "misc": 40.0},
    "adventure": {"food": 30.0, "transport": 20.0, "activities": 45.0, "misc": 12.0},
    "family": {"food": 38.0, "transport": 18.0, "activities": 30.0, "misc": 15.0},
    "business": {"food": 65.0, "transport": 35.0, "activities": 20.0, "misc": 25.0},
    "relaxed": {"food": 45.0, "transport": 14.0, "activities": 22.0, "misc": 14.0},
}

_CHILD_DISCOUNT = 0.7


class BudgetAgent(BaseAgent):
    name = BUDGET_AGENT
    provider_kind = "search"

    async def execute(self, state: TravelState) -> None:
        constraints = self.constraints(state)
        currency = (constraints.get("currency") or "USD").upper()
        travelers = max(int(constraints.get("travelers") or 1), 1)
        nights = int(constraints.get("nights") or 0)
        days = int(constraints.get("trip_days") or max(nights + 1, 1))
        style = constraints.get("travel_style") or "comfort"
        allowance = _DAILY_ALLOWANCE.get(style, _DAILY_ALLOWANCE["comfort"])

        analysis = BudgetAnalysis(
            currency=currency,
            total_budget=float(constraints["budget"]) if constraints.get("budget") else None,
        )
        breakdown = BudgetBreakdown()
        provenance: dict[str, BudgetLine] = {}
        confirmed = 0.0
        estimated = 0.0
        notes: list[str] = []

        # ---- flights -----------------------------------------------------
        flight_cost, flight_source, flight_basis = self._flight_cost(state, travelers)
        breakdown.flights = flight_cost
        provenance["flights"] = BudgetLine(
            amount=flight_cost, source=flight_source, basis=flight_basis
        )
        confirmed, estimated = self._bucket(flight_cost, flight_source, confirmed, estimated)

        # ---- hotels ------------------------------------------------------
        hotel_cost, hotel_source, hotel_basis = self._hotel_cost(state, nights, travelers)
        breakdown.hotels = hotel_cost
        provenance["hotels"] = BudgetLine(
            amount=hotel_cost, source=hotel_source, basis=hotel_basis
        )
        confirmed, estimated = self._bucket(hotel_cost, hotel_source, confirmed, estimated)

        # ---- daily allowances --------------------------------------------
        billable = self._billable_travelers(travelers, constraints)
        for key, label in (
            ("food", "food"),
            ("transport", "transport"),
            ("activities", "activities"),
        ):
            amount = round(allowance[key] * billable * days, 2)
            setattr(breakdown, label, amount)
            provenance[label] = BudgetLine(
                amount=amount,
                source=SOURCE_ESTIMATE,
                basis=f"{allowance[key]:.0f}/person/day for a {style} trip over {days} day(s)",
            )
            estimated += amount

        misc = round(allowance["misc"] * billable * days, 2)
        breakdown.miscellaneous = misc
        provenance["miscellaneous"] = BudgetLine(
            amount=misc, source=SOURCE_ESTIMATE, basis="contingency and incidentals"
        )
        estimated += misc

        # ---- itinerary activity costs override the allowance -------------
        itinerary_cost = self._itinerary_activity_cost(state)
        if itinerary_cost is not None and itinerary_cost > 0:
            estimated -= breakdown.activities
            breakdown.activities = round(itinerary_cost, 2)
            estimated += breakdown.activities
            provenance["activities"] = BudgetLine(
                amount=breakdown.activities,
                source=SOURCE_ESTIMATE,
                basis="sum of the estimated activity costs in the planned itinerary",
            )

        analysis.breakdown = breakdown
        analysis.line_provenance = provenance
        analysis.estimated_total = breakdown.total
        analysis.confirmed_cost_total = round(confirmed, 2)
        analysis.estimated_cost_total = round(estimated, 2)
        analysis.per_traveler_total = round(breakdown.total / travelers, 2) if travelers else None

        analysis.budget_status, status_note = self._status(analysis, days, nights)
        if status_note:
            notes.append(status_note)
        if analysis.total_budget is not None:
            analysis.remaining_budget = round(analysis.total_budget - analysis.estimated_total, 2)

        if confirmed == 0:
            notes.append(
                "No provider-confirmed price was available, so every line is a JourneyMesh estimate."
            )
        analysis.notes = notes
        analysis.recommendations = self._recommendations(analysis, state, constraints)

        state["budget_analysis"] = analysis.model_dump(mode="json")
        self.note(
            state,
            f"Estimated total {analysis.estimated_total:.0f} {currency} "
            f"({analysis.budget_status.replace('_', ' ')}).",
        )

    # ---- cost lines ------------------------------------------------------
    def _bucket(
        self, amount: float, source: str, confirmed: float, estimated: float
    ) -> tuple[float, float]:
        if source in (SOURCE_LIVE, SOURCE_SEARCH_DERIVED):
            return confirmed + amount, estimated
        return confirmed, estimated + amount

    def _flight_cost(self, state: TravelState, travelers: int) -> tuple[float, str, str]:
        flights = state.get("flight_results") or {}
        options = flights.get("options") or []
        priced = [
            option
            for option in options
            if option.get("price_per_traveler") is not None
        ]
        if not priced:
            return 0.0, SOURCE_ESTIMATE, "no fare was available from any provider"

        cheapest = min(priced, key=lambda option: option["price_per_traveler"])
        amount = round(float(cheapest["price_per_traveler"]) * travelers, 2)
        source = cheapest.get("price_source") or SOURCE_ESTIMATE
        basis = (
            f"{cheapest.get('airline') or 'best option'} at "
            f"{cheapest['price_per_traveler']:.0f} per traveller x {travelers}"
        )
        return amount, source, basis

    def _hotel_cost(
        self, state: TravelState, nights: int, travelers: int
    ) -> tuple[float, str, str]:
        hotels = state.get("hotel_results") or {}
        options = hotels.get("options") or []
        if not options or nights <= 0:
            return 0.0, SOURCE_ESTIMATE, "no accommodation was priced for this journey"

        index = min(int(hotels.get("recommended_index") or 0), len(options) - 1)
        chosen = options[index]
        nightly = chosen.get("price_per_night")
        if nightly is None:
            return 0.0, SOURCE_ESTIMATE, "the recommended stay did not publish a nightly rate"

        rooms = max(1, (travelers + 1) // 2) if travelers > 2 else 1
        amount = round(float(nightly) * nights * rooms, 2)
        source = chosen.get("price_source") or SOURCE_ESTIMATE
        basis = f"{nightly:.0f}/night x {nights} night(s)" + (f" x {rooms} rooms" if rooms > 1 else "")
        return amount, source, basis

    def _itinerary_activity_cost(self, state: TravelState) -> float | None:
        itinerary = state.get("itinerary_plan") or {}
        days = itinerary.get("days") or []
        if not days:
            return None
        total = 0.0
        for day in days:
            for slot in day.get("slots", []):
                for activity in slot.get("activities", []):
                    total += float(activity.get("estimated_cost") or 0)
        return total or None

    def _billable_travelers(self, travelers: int, constraints: dict[str, Any]) -> float:
        """Children are counted at a reduced rate for daily allowances."""
        special = (constraints.get("special_requirements") or "").lower()
        interests = set(constraints.get("interests") or [])
        family = constraints.get("travel_style") == "family" or "family_activities" in interests
        if family and travelers >= 3 and ("child" in special or "kid" in special or family):
            adults = max(2, travelers - 2)
            children = travelers - adults
            return adults + children * _CHILD_DISCOUNT
        return float(travelers)

    # ---- verdict ---------------------------------------------------------
    def _status(self, analysis: BudgetAnalysis, days: int, nights: int) -> tuple[str, str | None]:
        if analysis.total_budget is None:
            return (
                BUDGET_INSUFFICIENT,
                "No budget was provided, so the total below is a planning estimate only.",
            )
        if analysis.estimated_total <= 0:
            return BUDGET_INSUFFICIENT, "Not enough cost information was available."

        ratio = analysis.estimated_total / analysis.total_budget
        if ratio > 1.0:
            return (
                BUDGET_OVER,
                f"The plan is about {analysis.estimated_total - analysis.total_budget:.0f} "
                f"{analysis.currency} over the stated budget.",
            )
        if ratio >= NEAR_LIMIT_THRESHOLD:
            return (
                BUDGET_NEAR_LIMIT,
                "The plan uses almost the whole budget - leave room for incidentals.",
            )
        return BUDGET_WITHIN, None

    def _recommendations(
        self, analysis: BudgetAnalysis, state: TravelState, constraints: dict[str, Any]
    ) -> list[str]:
        recommendations: list[str] = []
        breakdown = analysis.breakdown

        if analysis.budget_status == BUDGET_OVER:
            overshoot = analysis.estimated_total - (analysis.total_budget or 0)
            hotels = state.get("hotel_results") or {}
            options = hotels.get("options") or []
            cheaper = [
                option
                for option in options[1:]
                if option.get("price_per_night") is not None
            ]
            if cheaper:
                cheapest = min(cheaper, key=lambda option: option["price_per_night"])
                nights = int(constraints.get("nights") or 1)
                saving = breakdown.hotels - float(cheapest["price_per_night"]) * nights
                if saving > 0:
                    recommendations.append(
                        f"Switching to {cheapest['name']} would save about {saving:.0f} "
                        f"{analysis.currency}."
                    )
            if breakdown.activities > overshoot:
                recommendations.append(
                    "Replacing two paid attractions with free walking routes closes most of the gap."
                )
            recommendations.append(
                "Moving the departure by a few days often reduces the largest cost line, the flights."
            )
        elif analysis.budget_status == BUDGET_NEAR_LIMIT:
            recommendations.append(
                "Keep about 10 percent of the budget unallocated for transfers and tips."
            )
        elif analysis.budget_status == BUDGET_WITHIN and analysis.remaining_budget:
            recommendations.append(
                f"About {analysis.remaining_budget:.0f} {analysis.currency} is unspent - "
                "it covers a guided day trip or an upgrade to a more central stay."
            )

        if analysis.confirmed_cost_total == 0:
            recommendations.append(
                "Confirm flight and hotel prices with the provider before committing to this budget."
            )
        return recommendations
