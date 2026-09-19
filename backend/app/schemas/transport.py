"""How a traveller gets from origin to destination, by any mode.

Every figure here is a planning estimate from distance and regional rates -
there is no bus, train or ferry booking provider behind it - and says so.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import DataSource, TravelCrewModel

TransportMode = Literal[
    "flight",
    "train",
    "bus",
    "car",
    "cng",
    "auto_rickshaw",
    "tuk_tuk",
    "rickshaw",
    "taxi",
    "ferry",
]

# What a traveller can ask for up front. "auto" lets the planner choose.
TransportPreference = Literal["auto", "flight", "train", "bus", "car"]

TRANSPORT_PREFERENCES: tuple[str, ...] = ("auto", "flight", "train", "bus", "car")


class TransportLeg(TravelCrewModel):
    mode: TransportMode
    from_place: str
    to_place: str
    distance_km: float
    duration_hours: float
    # Per person for seats (flight, train, bus, ferry); the whole party's
    # share of however many vehicles it needs for car, CNG, auto and taxi.
    cost_per_traveler: float
    cost_for_group: float
    vehicles: int | None = None
    note: str | None = None


class TransportOption(TravelCrewModel):
    # The mode that carries the long part of the journey.
    main_mode: TransportMode
    label: str
    legs: list[TransportLeg] = Field(default_factory=list)
    distance_km: float
    duration_hours: float
    one_way_per_traveler: float
    one_way_for_group: float
    # Both directions when the journey has a return date.
    trip_total_for_group: float
    recommended: bool = False
    reason: str | None = None


class RoutePlan(TravelCrewModel):
    origin: str | None = None
    destination: str | None = None
    preference: TransportPreference = "auto"
    round_trip: bool = False
    travelers: int = 1
    straight_line_km: float | None = None
    options: list[TransportOption] = Field(default_factory=list)
    recommended_index: int | None = None
    currency: str = "USD"
    source: DataSource = "ESTIMATE"
    notes: list[str] = Field(default_factory=list)

    @property
    def recommended(self) -> TransportOption | None:
        if self.recommended_index is None or not self.options:
            return None
        return self.options[self.recommended_index]
