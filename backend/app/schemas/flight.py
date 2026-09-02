"""Flight schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import DataSource, JourneyMeshModel, Provenance


class FlightSegment(JourneyMeshModel):
    departure_airport: str | None = None
    departure_iata: str | None = None
    arrival_airport: str | None = None
    arrival_iata: str | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    duration: str | None = None


class FlightOption(JourneyMeshModel):
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


class AirportMatch(JourneyMeshModel):
    city: str
    iata: str | None = None
    name: str | None = None
    country: str | None = None
    confidence: float = 0.0


class FlightResults(JourneyMeshModel):
    origin: str | None = None
    destination: str | None = None
    origin_airports: list[AirportMatch] = Field(default_factory=list)
    destination_airports: list[AirportMatch] = Field(default_factory=list)
    options: list[FlightOption] = Field(default_factory=list)
    cheapest_total: float | None = None
    currency: str | None = None
    source: DataSource = "UNAVAILABLE"
    notes: list[str] = Field(default_factory=list)
