"""Flight schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.common import DataSource, JourneyMeshModel, Provenance


class FlightSegment(JourneyMeshModel):
    departure_airport: Optional[str] = None
    departure_iata: Optional[str] = None
    arrival_airport: Optional[str] = None
    arrival_iata: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    duration: Optional[str] = None


class FlightOption(JourneyMeshModel):
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    origin_iata: Optional[str] = None
    destination_iata: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    stops: int = 0
    segments: list[FlightSegment] = Field(default_factory=list)
    cabin: Optional[str] = None
    price_per_traveler: Optional[float] = None
    currency: Optional[str] = None
    price_source: DataSource = "UNAVAILABLE"
    booking_hint: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class AirportMatch(JourneyMeshModel):
    city: str
    iata: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    confidence: float = 0.0


class FlightResults(JourneyMeshModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    origin_airports: list[AirportMatch] = Field(default_factory=list)
    destination_airports: list[AirportMatch] = Field(default_factory=list)
    options: list[FlightOption] = Field(default_factory=list)
    cheapest_total: Optional[float] = None
    currency: Optional[str] = None
    source: DataSource = "UNAVAILABLE"
    notes: list[str] = Field(default_factory=list)
