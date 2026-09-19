"""Flight schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import DataSource, Provenance, TravelCrewModel
from app.schemas.transport import RoutePlan


class FlightSegment(TravelCrewModel):
    departure_airport: str | None = None
    departure_iata: str | None = None
    arrival_airport: str | None = None
    arrival_iata: str | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    duration: str | None = None


class FlightOption(TravelCrewModel):
    airline: str | None = None
    flight_number: str | None = None
    origin_iata: str | None = None
    destination_iata: str | None = None
    departure_date: str | None = None
    return_date: str | None = None
    stops: int = 0
    segments: list[FlightSegment] = Field(default_factory=list)
    cabin: str | None = None
    price_per_traveler: float | None = None
    currency: str | None = None
    price_source: DataSource = "UNAVAILABLE"
    booking_hint: str | None = None
    provenance: Provenance = Field(default_factory=Provenance)


class AirportMatch(TravelCrewModel):
    city: str
    iata: str | None = None
    name: str | None = None
    country: str | None = None
    confidence: float = 0.0


class FlightResults(TravelCrewModel):
    origin: str | None = None
    destination: str | None = None
    origin_airports: list[AirportMatch] = Field(default_factory=list)
    destination_airports: list[AirportMatch] = Field(default_factory=list)
    options: list[FlightOption] = Field(default_factory=list)
    cheapest_total: float | None = None
    currency: str | None = None
    source: DataSource = "UNAVAILABLE"
    notes: list[str] = Field(default_factory=list)
    # Every way to get there - flight, train, bus, car, ferry and the local
    # hops between them - with the one that suits this party marked.
    route_plan: RoutePlan | None = None
