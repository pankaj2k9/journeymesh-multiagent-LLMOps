"""Final Response Agent.

Runs only after a human approves the draft. It combines the approved slices
of the state into one structured, validated journey and renders every
generated sentence in the traveller's chosen language (en, bn, hi) from the
server-side phrase catalogue - so the output does not depend on a translation
model being available.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import (
    BUDGET_INSUFFICIENT,
    BUDGET_NEAR_LIMIT,
    BUDGET_OVER,
    BUDGET_WITHIN,
    DEFAULT_LANGUAGE,
    FINAL_RESPONSE_AGENT,
    SOURCE_ESTIMATE,
    SOURCE_LIVE,
    SUPPORTED_LANGUAGES,
)
from app.core.i18n import translate, translate_all
from app.graph.state import TravelState
from app.schemas.budget import BudgetAnalysis
from app.schemas.common import ProviderStatus
from app.schemas.flight import FlightResults
from app.schemas.hotel import HotelResults
from app.schemas.itinerary import ItineraryPlan
from app.schemas.travel import FinalJourney, JourneyOverview
from app.schemas.weather import WeatherInfo


class FinalResponseAgent(BaseAgent):
    name = FINAL_RESPONSE_AGENT

    async def execute(self, state: TravelState) -> None:
        constraints = self.constraints(state)
        language = self._language(state)

        flights = FlightResults.model_validate(state.get("flight_results") or {})
        hotels = HotelResults.model_validate(state.get("hotel_results") or {})
        weather = WeatherInfo.model_validate(state.get("weather_info") or {})
        budget = BudgetAnalysis.model_validate(state.get("budget_analysis") or {})
        itinerary = ItineraryPlan.model_validate(state.get("itinerary_plan") or {})

        overview = self._overview(state, constraints, itinerary, language)
        tips = self._tips(itinerary, budget, flights, hotels, language)

        journey = FinalJourney(
            trip_id=state.get("trip_id", ""),
            language=language,  # type: ignore[arg-type]
            overview=overview,
            flights=flights,
            hotels=hotels,
            weather=weather,
            budget=budget,
            itinerary=itinerary,
            travel_tips=tips,
            provider_status=[
                ProviderStatus.model_validate(item)
                for item in (state.get("provider_status") or [])
            ],
            closing_note=self._closing(flights, hotels, language),
        )

        # Localise the weather advice that is shown alongside the journey.
        journey.weather.packing_recommendations = translate_all(
            weather.packing_codes, language
        ) or weather.packing_recommendations
        journey.weather.travel_suggestions = translate_all(
            weather.suggestion_codes, language
        ) or weather.travel_suggestions

        state["final_response"] = journey.model_dump(mode="json")
        self.note(state, f"Final journey assembled in '{language}'.")

    # ---- helpers ---------------------------------------------------------
    def _language(self, state: TravelState) -> str:
        constraints = state.get("trip_constraints") or {}
        language = (
            constraints.get("response_language")
            or state.get("response_language")
            or DEFAULT_LANGUAGE
        )
        return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    def _overview(
        self,
        state: TravelState,
        constraints: dict[str, Any],
        itinerary: ItineraryPlan,
        language: str,
    ) -> JourneyOverview:
        destination = constraints.get("destination") or itinerary.destination or "-"
        days = itinerary.total_days or constraints.get("trip_days")
        travelers = int(constraints.get("travelers") or 1)
        style_key = f"style.{constraints.get('travel_style') or 'comfort'}"
        style = translate(style_key, language)

        if days:
            title = translate("journey.title", language, days=days, destination=destination)
        else:
            title = translate("journey.title_no_days", language, destination=destination)

        interests = [
            translate(f"interest.{item}", language)
            for item in (constraints.get("interests") or [])
        ]
        if interests:
            headline = translate(
                "journey.headline",
                language,
                style=style,
                travelers=travelers,
                interests=", ".join(interests),
            )
        else:
            headline = translate(
                "journey.headline_simple", language, style=style, travelers=travelers
            )

        return JourneyOverview(
            title=title,
            headline=headline,
            origin=constraints.get("origin"),
            destination=destination,
            departure_date=str(constraints["departure_date"])
            if constraints.get("departure_date")
            else None,
            return_date=str(constraints["return_date"])
            if constraints.get("return_date")
            else None,
            travelers=travelers,
            nights=constraints.get("nights"),
            travel_style=constraints.get("travel_style"),
            language=language,  # type: ignore[arg-type]
        )

    def _tips(
        self,
        itinerary: ItineraryPlan,
        budget: BudgetAnalysis,
        flights: FlightResults,
        hotels: HotelResults,
        language: str,
    ) -> list[str]:
        codes: list[Any] = list(itinerary.travel_tip_codes)

        if budget.budget_status == BUDGET_WITHIN and budget.remaining_budget:
            codes.append(
                [
                    "budget.within",
                    {"remaining": f"{budget.remaining_budget:.0f}", "currency": budget.currency},
                ]
            )
        elif budget.budget_status == BUDGET_NEAR_LIMIT:
            codes.append("budget.near_limit")
        elif budget.budget_status == BUDGET_OVER and budget.total_budget is not None:
            codes.append(
                [
                    "budget.over",
                    {
                        "over": f"{budget.estimated_total - budget.total_budget:.0f}",
                        "currency": budget.currency,
                    },
                ]
            )
        elif budget.budget_status == BUDGET_INSUFFICIENT:
            codes.append("budget.insufficient")

        sources = {flights.source, hotels.source}
        if SOURCE_ESTIMATE in sources:
            codes.append("provenance.estimates")
        if SOURCE_LIVE in sources:
            codes.append("provenance.live")

        return translate_all(codes, language)

    def _closing(self, flights: FlightResults, hotels: HotelResults, language: str) -> str:
        estimated = SOURCE_ESTIMATE in {flights.source, hotels.source}
        code = "journey.closing_estimates" if estimated else "journey.closing"
        return translate(code, language)
