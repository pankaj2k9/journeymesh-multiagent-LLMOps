"""The structured search brief for one trip.

``TripPlanRequest`` describes a *planning* request and is unchanged. This is
what a *search* takes: the fields a flight, hotel or activity provider actually
needs, validated server-side so a provider adapter never has to ask whether a
child age is plausible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.core.constants import (
    ACCOMMODATION_TYPES,
    BAGGAGE_OPTIONS,
    CABIN_CLASSES,
    CHILD_MAX_AGE,
    INTERESTS,
    MAX_ADULTS,
    MAX_CHILDREN,
    MAX_FLEXIBLE_DAYS,
    MAX_PREFERRED_AIRLINES,
    MAX_STOPS_CEILING,
    TRAVEL_PACES,
)
from app.schemas.common import TravelCrewModel

CabinClass = Literal["economy", "premium_economy", "business", "first"]
TravelPace = Literal["relaxed", "balanced", "packed"]
BaggageOption = Literal["none", "cabin_only", "checked"]

assert set(CABIN_CLASSES) == set(CabinClass.__args__)  # type: ignore[attr-defined]
assert set(TRAVEL_PACES) == set(TravelPace.__args__)  # type: ignore[attr-defined]
assert set(BAGGAGE_OPTIONS) == set(BaggageOption.__args__)  # type: ignore[attr-defined]

# IATA airline designators are two characters, occasionally three.
_AIRLINE_CODE_MAX = 3


def _clean_airlines(value: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in value:
        code = item.strip().upper()
        if not code:
            continue
        if len(code) > _AIRLINE_CODE_MAX or not code.isalnum():
            raise ValueError(f"{item!r} is not an airline code")
        if code not in cleaned:
            cleaned.append(code)
    return cleaned


class TripPreferenceIn(TravelCrewModel):
    """Everything a traveller can specify about how they want to travel."""

    # ---- who ------------------------------------------------------------
    adults: int = Field(default=1, ge=1, le=MAX_ADULTS)
    children: int = Field(default=0, ge=0, le=MAX_CHILDREN)
    child_ages: list[int] = Field(default_factory=list, max_length=MAX_CHILDREN)

    # ---- when -----------------------------------------------------------
    flexible_days: int = Field(default=0, ge=0, le=MAX_FLEXIBLE_DAYS)
    flexible_destination: bool = False

    # ---- flying ---------------------------------------------------------
    cabin_class: CabinClass = "economy"
    max_stops: int | None = Field(default=None, ge=0, le=MAX_STOPS_CEILING)
    baggage: BaggageOption = "cabin_only"
    preferred_airlines: list[str] = Field(
        default_factory=list, max_length=MAX_PREFERRED_AIRLINES
    )
    excluded_airlines: list[str] = Field(
        default_factory=list, max_length=MAX_PREFERRED_AIRLINES
    )
    earliest_departure_hour: int | None = Field(default=None, ge=0, le=23)
    latest_arrival_hour: int | None = Field(default=None, ge=0, le=23)

    # ---- staying --------------------------------------------------------
    accommodation_type: str = "any"
    hotel_min_rating: float | None = Field(default=None, ge=0, le=5)

    # ---- doing ----------------------------------------------------------
    pace: TravelPace = "balanced"
    interests: list[str] = Field(default_factory=list, max_length=len(INTERESTS))
    dietary_requirements: str | None = Field(default=None, max_length=500)
    accessibility_requirements: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("accommodation_type")
    @classmethod
    def _known_accommodation(cls, value: str) -> str:
        normalised = value.strip().lower().replace(" ", "_")
        if normalised not in ACCOMMODATION_TYPES:
            raise ValueError(
                f"accommodation_type must be one of {', '.join(ACCOMMODATION_TYPES)}"
            )
        return normalised

    @field_validator("interests")
    @classmethod
    def _known_interests(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            normalised = item.strip().lower().replace(" ", "_")
            if normalised not in INTERESTS:
                raise ValueError(f"unsupported interest: {item}")
            if normalised not in cleaned:
                cleaned.append(normalised)
        return cleaned

    @field_validator("preferred_airlines", "excluded_airlines")
    @classmethod
    def _airline_codes(cls, value: list[str]) -> list[str]:
        return _clean_airlines(value)

    @field_validator("child_ages")
    @classmethod
    def _plausible_ages(cls, value: list[int]) -> list[int]:
        for age in value:
            if age < 0 or age > CHILD_MAX_AGE:
                raise ValueError(
                    f"a child's age must be between 0 and {CHILD_MAX_AGE}; "
                    "an older traveller counts as an adult"
                )
        return value

    @model_validator(mode="after")
    def _coherent(self) -> TripPreferenceIn:
        if self.children and not self.child_ages:
            raise ValueError(
                "child_ages is required when the party includes children - "
                "fares and room occupancy both depend on them"
            )
        if self.child_ages and len(self.child_ages) != self.children:
            raise ValueError(
                f"{self.children} child(ren) declared but {len(self.child_ages)} age(s) given"
            )
        overlap = set(self.preferred_airlines) & set(self.excluded_airlines)
        if overlap:
            raise ValueError(
                f"{', '.join(sorted(overlap))} is both preferred and excluded"
            )
        return self

    @property
    def travelers(self) -> int:
        return self.adults + self.children


class TripPreferenceOut(TripPreferenceIn):
    trip_id: str
    travelers_total: int = 1
    updated_at: datetime | None = None
