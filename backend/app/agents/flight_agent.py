"""Flight Agent.

Resolves airports, retrieves route information through the aviation MCP tool
and normalises whatever the provider returned. It never invents a flight
number, a schedule, an availability or a fare - anything that is not
provider-confirmed is labelled as an estimate with its basis stated.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import FLIGHT_AGENT, SOURCE_ESTIMATE, SOURCE_LIVE, SOURCE_UNAVAILABLE
from app.graph.state import TravelState
from app.schemas.flight import FlightResults


class FlightAgent(BaseAgent):
    name = FLIGHT_AGENT
    provider_kind = "flights"

    async def execute(self, state: TravelState) -> None:
        constraints = self.constraints(state)
        origin = constraints.get("origin")
        destination = constraints.get("destination")

        if not destination:
            state["flight_results"] = FlightResults(
                source=SOURCE_UNAVAILABLE,
                notes=["No destination was provided, so no route could be researched."],
            ).model_dump(mode="json")
            self.note(state, "Skipped: the journey has no destination yet.")
            return

        if not origin:
            state["flight_results"] = FlightResults(
                destination=destination,
                source=SOURCE_UNAVAILABLE,
                notes=[
                    "No departure city was provided. Add one and JourneyMesh will "
                    "research routes and fares."
                ],
            ).model_dump(mode="json")
            self.note(state, "Skipped: no departure city was provided.")
            return

        origin_airport = await self.call_tool(
            state,
            "lookup_airport",
            {"city": origin},
            provider="aviation_mcp",
        )
        destination_airport = await self.call_tool(
            state,
            "lookup_airport",
            {"city": destination},
            provider="aviation_mcp",
        )

        arguments: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "travelers": int(constraints.get("travelers") or 1),
        }
        if constraints.get("departure_date"):
            arguments["departure_date"] = str(constraints["departure_date"])
        if constraints.get("return_date"):
            arguments["return_date"] = str(constraints["return_date"])

        result = await self.call_tool(
            state, "search_flights", arguments, provider="aviation_mcp"
        )

        if not result.ok:
            state["flight_results"] = FlightResults(
                origin=origin,
                destination=destination,
                source=SOURCE_UNAVAILABLE,
                notes=["Flight research was unavailable for this journey."],
            ).model_dump(mode="json")
            return

        payload = dict(result.data)
        if origin_airport.ok and origin_airport.data.get("iata"):
            payload["origin_airports"] = [origin_airport.data]
        if destination_airport.ok and destination_airport.data.get("iata"):
            payload["destination_airports"] = [destination_airport.data]

        flights = FlightResults.model_validate(payload)
        flights.options.sort(key=lambda option: (option.price_per_traveler or 1e9, option.stops))
        if flights.options:
            travelers = max(int(constraints.get("travelers") or 1), 1)
            priced = [o.price_per_traveler for o in flights.options if o.price_per_traveler]
            flights.cheapest_total = round(min(priced) * travelers, 2) if priced else None
            flights.currency = "USD" if priced else None

        state["flight_results"] = flights.model_dump(mode="json")

        if flights.source == SOURCE_LIVE:
            summary = f"{len(flights.options)} live route option(s) retrieved."
        elif flights.source == SOURCE_ESTIMATE:
            summary = (
                f"{len(flights.options)} route option(s) prepared from JourneyMesh "
                "reference data - fares are planning estimates."
            )
        else:
            summary = "No route information could be retrieved."
        self.note(state, summary)
