"""What a search asks for.

These are the criteria an adapter receives. They are deliberately provider-
neutral and fully validated here, so no adapter has to decide whether a max-
stops of 47 is plausible, and no model output reaches a provider unchecked.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.core.constants import (
    BAGGAGE_OPTIONS,
    MAX_ADULTS,
    MAX_CHILDREN,
    MAX_FLEXIBLE_DAYS,
    MAX_PREFERRED_AIRLINES,
    MAX_STOPS_CEILING,
    SUPPORTED_CURRENCIES,
)
from app.schemas.common import TravelCrewModel
from app.schemas.money import OptionalMoney
from app.schemas.offers import (
    ActivityOffer,
    Badge,
    CabinClass,
    FlightOffer,
    HotelOffer,
    SortMode,
)

# A search returns a page, not a catalogue. Wide enough to rank meaningfully,
# small enough that a provider call stays one round trip.
MAX_RESULTS = 50
DEFAULT_RESULTS = 20


def _clean_airlines(value: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in value:
        code = item.strip().upper()
        if not code:
            continue
        if len(code) > 3 or not code.isalnum():
            raise ValueError(f"{item!r} is not an airline code")
        if code not in cleaned:
            cleaned.append(code)
    return cleaned


class FlightSearchCriteria(TravelCrewModel):
    """A normalised flight search."""

    origin: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    departure_date: date
    return_date: date | None = None

    adults: int = Field(default=1, ge=1, le=MAX_ADULTS)
    children: int = Field(default=0, ge=0, le=MAX_CHILDREN)
    child_ages: list[int] = Field(default_factory=list, max_length=MAX_CHILDREN)

    cabin_class: CabinClass = "economy"
    max_stops: int | None = Field(default=None, ge=0, le=MAX_STOPS_CEILING)
    baggage: str = "cabin_only"

    preferred_airlines: list[str] = Field(
        default_factory=list, max_length=MAX_PREFERRED_AIRLINES
    )
    excluded_airlines: list[str] = Field(
        default_factory=list, max_length=MAX_PREFERRED_AIRLINES
    )

    # Shift both dates by up to this many days and search the window.
    flexible_days: int = Field(default=0, ge=0, le=MAX_FLEXIBLE_DAYS)
    # Include nearby airports for either end.
    include_nearby_airports: bool = False

    earliest_departure_hour: int | None = Field(default=None, ge=0, le=23)
    latest_departure_hour: int | None = Field(default=None, ge=0, le=23)
    earliest_arrival_hour: int | None = Field(default=None, ge=0, le=23)
    latest_arrival_hour: int | None = Field(default=None, ge=0, le=23)

    # A ceiling on the flight line specifically, not on the whole trip.
    max_total_price: OptionalMoney = None
    currency: str = "USD"

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        upper = value.upper()
        if upper not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        return upper

    @field_validator("baggage")
    @classmethod
    def _known_baggage(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in BAGGAGE_OPTIONS:
            raise ValueError(f"baggage must be one of {', '.join(BAGGAGE_OPTIONS)}")
        return normalised

    @field_validator("preferred_airlines", "excluded_airlines")
    @classmethod
    def _airline_codes(cls, value: list[str]) -> list[str]:
        return _clean_airlines(value)

    @model_validator(mode="after")
    def _coherent(self) -> FlightSearchCriteria:
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("return_date must not be earlier than departure_date")
        if self.origin.strip().lower() == self.destination.strip().lower():
            raise ValueError("origin and destination must be different")
        if self.children and len(self.child_ages) != self.children:
            raise ValueError(
                f"{self.children} child(ren) declared but {len(self.child_ages)} age(s) given"
            )
        overlap = set(self.preferred_airlines) & set(self.excluded_airlines)
        if overlap:
            raise ValueError(f"{', '.join(sorted(overlap))} is both preferred and excluded")
        return self

    @property
    def travelers(self) -> int:
        return self.adults + self.children

    @property
    def round_trip(self) -> bool:
        return self.return_date is not None

    def cache_key(self) -> str:
        """A stable identity for this search.

        Used to seed the offline provider so the same search always produces
        the same offers, and later to recognise a repeat search as cacheable.
        """
        parts = [
            self.origin.strip().lower(),
            self.destination.strip().lower(),
            self.departure_date.isoformat(),
            self.return_date.isoformat() if self.return_date else "-",
            f"{self.adults}a{self.children}c",
            self.cabin_class,
            self.baggage,
            str(self.max_stops if self.max_stops is not None else "-"),
            ",".join(self.preferred_airlines) or "-",
            ",".join(self.excluded_airlines) or "-",
            str(self.flexible_days),
            self.currency,
        ]
        return "|".join(parts)


class HotelSearchCriteria(TravelCrewModel):
    destination: str = Field(min_length=2, max_length=120)
    check_in: date
    check_out: date

    adults: int = Field(default=1, ge=1, le=MAX_ADULTS)
    children: int = Field(default=0, ge=0, le=MAX_CHILDREN)
    child_ages: list[int] = Field(default_factory=list, max_length=MAX_CHILDREN)
    rooms: int = Field(default=1, ge=1, le=5)

    accommodation_type: str = "any"
    min_star_rating: float | None = Field(default=None, ge=0, le=5)
    min_review_score: float | None = Field(default=None, ge=0, le=10)
    breakfast_required: bool = False
    free_cancellation_required: bool = False
    max_distance_km: float | None = Field(default=None, ge=0, le=50)

    # A ceiling on the whole stay, not on the nightly rate. Travellers are
    # shown a nightly rate and charged a stay total, and this is the one that
    # can actually break a budget.
    max_total_stay: OptionalMoney = None
    currency: str = "USD"

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        upper = value.upper()
        if upper not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        return upper

    @model_validator(mode="after")
    def _coherent(self) -> HotelSearchCriteria:
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        if self.children and len(self.child_ages) != self.children:
            raise ValueError(
                f"{self.children} child(ren) declared but {len(self.child_ages)} age(s) given"
            )
        return self

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def guests(self) -> int:
        return self.adults + self.children

    def cache_key(self) -> str:
        return "|".join(
            [
                self.destination.strip().lower(),
                self.check_in.isoformat(),
                self.check_out.isoformat(),
                f"{self.adults}a{self.children}c{self.rooms}r",
                self.accommodation_type,
                str(self.min_star_rating or "-"),
                self.currency,
            ]
        )


class ActivitySearchCriteria(TravelCrewModel):
    destination: str = Field(min_length=2, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    participants: int = Field(default=1, ge=1, le=MAX_ADULTS + MAX_CHILDREN)
    categories: list[str] = Field(default_factory=list, max_length=10)
    max_price_per_person: OptionalMoney = None
    currency: str = "USD"

    @model_validator(mode="after")
    def _coherent(self) -> ActivitySearchCriteria:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self

    def cache_key(self) -> str:
        return "|".join(
            [
                self.destination.strip().lower(),
                self.start_date.isoformat() if self.start_date else "-",
                self.end_date.isoformat() if self.end_date else "-",
                str(self.participants),
                ",".join(sorted(self.categories)) or "-",
                self.currency,
            ]
        )


# ---- results ------------------------------------------------------------
class BudgetSnapshotForOffer(TravelCrewModel):
    """The budget lines shown on one result card.

    Carried per offer rather than computed in the interface, so "46% of trip
    budget / $2,164 remaining" comes from the budget engine and cannot drift
    from what selecting the offer would actually do.
    """

    total_budget: OptionalMoney = None
    percentage_of_budget: float | None = None
    remaining_after: OptionalMoney = None
    within_budget: bool | None = None
    currency: str = "USD"


class RankedFlightOffer(TravelCrewModel):
    offer: FlightOffer
    badges: list[Badge] = Field(default_factory=list)
    budget: BudgetSnapshotForOffer | None = None
    # Why this offer sits where it does, in one line, for the interface.
    rank_reason: str | None = None
    value_score: float | None = None


class RankedHotelOffer(TravelCrewModel):
    offer: HotelOffer
    badges: list[Badge] = Field(default_factory=list)
    budget: BudgetSnapshotForOffer | None = None
    rank_reason: str | None = None
    value_score: float | None = None


class RankedActivityOffer(TravelCrewModel):
    offer: ActivityOffer
    badges: list[Badge] = Field(default_factory=list)
    budget: BudgetSnapshotForOffer | None = None


class ProviderNote(TravelCrewModel):
    """What happened at the provider, in a form the interface can render.

    A search that fell back to the offline provider, or that dropped a
    provider that timed out, says so here. Silence would let mock data pass
    for live data, which is the one thing this system must never do.
    """

    provider: str
    ok: bool = True
    source: str = "MOCK"
    latency_ms: int | None = None
    message: str | None = None


class FlightSearchResults(TravelCrewModel):
    search_id: str | None = None
    trip_id: str | None = None
    criteria: FlightSearchCriteria
    sort: SortMode = "cheapest"
    results: list[RankedFlightOffer] = Field(default_factory=list)
    total: int = 0
    currency: str = "USD"
    providers: list[ProviderNote] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HotelSearchResults(TravelCrewModel):
    search_id: str | None = None
    trip_id: str | None = None
    criteria: HotelSearchCriteria
    sort: SortMode = "cheapest"
    results: list[RankedHotelOffer] = Field(default_factory=list)
    total: int = 0
    currency: str = "USD"
    providers: list[ProviderNote] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ActivitySearchResults(TravelCrewModel):
    search_id: str | None = None
    trip_id: str | None = None
    criteria: ActivitySearchCriteria
    sort: SortMode = "cheapest"
    results: list[RankedActivityOffer] = Field(default_factory=list)
    total: int = 0
    currency: str = "USD"
    providers: list[ProviderNote] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


assert Decimal  # re-exported implicitly through the money annotations
