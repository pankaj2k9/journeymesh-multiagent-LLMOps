"""The internal offer schema.

Every travel provider has its own vocabulary. Amadeus calls a journey an
``itinerary`` and a leg a ``segment``; Duffel calls them a ``slice`` and a
``segment``; a hotel API might return a nightly rate with taxes folded in, or
beside it, or not at all. None of that belongs above the adapter layer.

So an adapter's job is to produce exactly these shapes, and the rest of the
application - ranking, budget, comparison, the interface - is written against
them alone. Two rules make that normalisation trustworthy:

  * **A price is a breakdown, never a single number.** Cheapest-first means
    cheapest *total payable*, and that can only be computed when base fare,
    taxes, mandatory fees and the baggage a traveller actually needs are
    separate fields. An adapter that cannot separate them says so rather than
    guessing.
  * **Every offer carries its provenance and its expiry.** ``source`` says
    whether this is a live quote, a cached one, an estimate or the offline
    mock, and ``expires_at`` says when the quote stops meaning anything. Both
    are read by the booking flow, so neither is decoration.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field, computed_field, model_validator

from app.core.constants import PAYABLE_SOURCES
from app.schemas.common import DataSource, TravelCrewModel, utcnow
from app.schemas.money import MoneyAmount, OptionalMoney

CabinClass = Literal["economy", "premium_economy", "business", "first"]
OfferKind = Literal["flight", "hotel", "activity"]

SortMode = Literal["cheapest", "best_value", "fastest", "fewest_stops", "rating", "distance", "recommended"]

Badge = Literal[
    "CHEAPEST",
    "BEST_VALUE",
    "FASTEST",
    "FEWEST_STOPS",
    "WITHIN_BUDGET",
    "OVER_BUDGET",
    "RECOMMENDED",
]

# How long a quote is assumed good for when a provider does not say. Short on
# purpose: an offer with no stated expiry is revalidated before booking, and a
# generous default would let a stale price reach a confirmation screen.
DEFAULT_OFFER_TTL = timedelta(minutes=20)


class PriceBreakdown(TravelCrewModel):
    """What one traveller pays, itemised.

    ``total`` is computed, not supplied, so an adapter cannot hand back parts
    that do not add up to the number a traveller is shown.
    """

    base_fare: MoneyAmount = Field(default=Decimal(0))
    taxes: MoneyAmount = Field(default=Decimal(0))
    # Mandatory charges a provider adds: carrier-imposed surcharges, booking
    # fees, resort fees. Optional extras never belong here.
    fees: MoneyAmount = Field(default=Decimal(0))
    # The cost of the baggage this search actually asked for. Zero when the
    # allowance is already included in the fare.
    baggage_fee: MoneyAmount = Field(default=Decimal(0))
    currency: str = "USD"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> Decimal:
        """Total payable per traveller. The number ranking sorts on."""
        return self.base_fare + self.taxes + self.fees + self.baggage_fee


class BaggageAllowance(TravelCrewModel):
    """What the fare includes, and what the search asked for.

    ``checked_included`` being False with a non-zero ``baggage_fee`` on the
    price is how a headline fare that excludes a bag stops being cheapest.
    """

    cabin_bags: int = 1
    checked_bags: int = 0
    checked_weight_kg: int | None = None
    checked_included: bool = False
    note: str | None = None


class FareConditions(TravelCrewModel):
    """Whether this money can be got back, and on what terms."""

    refundable: bool | None = None
    changeable: bool | None = None
    change_fee: OptionalMoney = None
    cancellation_deadline: datetime | None = None
    note: str | None = None


class OfferMeta(TravelCrewModel):
    """Where an offer came from, and how long it is good for."""

    provider: str
    source: DataSource = "MOCK"
    retrieved_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    # The provider's own identifier, needed to re-price or book this exact
    # offer later. Opaque to everything above the adapter.
    provider_offer_id: str | None = None
    booking_url: str | None = None

    @property
    def payable(self) -> bool:
        """Whether money quoted here could actually be charged."""
        return self.source in PAYABLE_SOURCES

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or utcnow()) >= self.expires_at


# ---- flights ------------------------------------------------------------
class FlightSegment(TravelCrewModel):
    """One take-off and landing."""

    marketing_airline: str | None = None
    marketing_airline_code: str | None = None
    operating_airline: str | None = None
    flight_number: str | None = None

    departure_iata: str | None = None
    departure_airport: str | None = None
    departure_time: datetime | None = None

    arrival_iata: str | None = None
    arrival_airport: str | None = None
    arrival_time: datetime | None = None

    duration_minutes: int | None = None
    cabin: CabinClass = "economy"
    aircraft: str | None = None


class Layover(TravelCrewModel):
    airport_iata: str | None = None
    airport_name: str | None = None
    duration_minutes: int | None = None
    # An overnight or airport-change connection is a real cost to a traveller
    # even when it costs nothing, so ranking is allowed to see it.
    overnight: bool = False
    changes_airport: bool = False


class FlightSlice(TravelCrewModel):
    """One direction of travel: outbound or return."""

    segments: list[FlightSegment] = Field(default_factory=list)
    layovers: list[Layover] = Field(default_factory=list)
    duration_minutes: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stops(self) -> int:
        return max(len(self.segments) - 1, 0)

    @property
    def origin_iata(self) -> str | None:
        return self.segments[0].departure_iata if self.segments else None

    @property
    def destination_iata(self) -> str | None:
        return self.segments[-1].arrival_iata if self.segments else None

    @property
    def departure_time(self) -> datetime | None:
        return self.segments[0].departure_time if self.segments else None

    @property
    def arrival_time(self) -> datetime | None:
        return self.segments[-1].arrival_time if self.segments else None


class FlightOffer(TravelCrewModel):
    """One bookable (or mock) flight itinerary for the whole party."""

    offer_id: str
    meta: OfferMeta

    slices: list[FlightSlice] = Field(default_factory=list)
    cabin: CabinClass = "economy"
    baggage: BaggageAllowance = Field(default_factory=BaggageAllowance)
    conditions: FareConditions = Field(default_factory=FareConditions)

    price_per_traveler: PriceBreakdown = Field(default_factory=PriceBreakdown)
    travelers: int = 1
    # Adults and children may be priced differently, so the group total is
    # supplied by the adapter rather than assumed to be per-head x heads.
    total_price: MoneyAmount = Field(default=Decimal(0))
    currency: str = "USD"

    seats_remaining: int | None = None

    @model_validator(mode="after")
    def _default_total(self) -> FlightOffer:
        if self.total_price == 0 and self.travelers:
            object.__setattr__(
                self, "total_price", self.price_per_traveler.total * self.travelers
            )
        return self

    # ---- what ranking and the result card read ---------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def stops(self) -> int:
        """Stops on the longest direction - what "1 stop" on a card means."""
        return max((slice_.stops for slice_ in self.slices), default=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_duration_minutes(self) -> int:
        return sum(slice_.duration_minutes or 0 for slice_ in self.slices)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def airlines(self) -> list[str]:
        names: list[str] = []
        for slice_ in self.slices:
            for segment in slice_.segments:
                name = segment.marketing_airline
                if name and name not in names:
                    names.append(name)
        return names

    @property
    def airline_codes(self) -> list[str]:
        codes: list[str] = []
        for slice_ in self.slices:
            for segment in slice_.segments:
                code = segment.marketing_airline_code
                if code and code not in codes:
                    codes.append(code)
        return codes

    @property
    def outbound(self) -> FlightSlice | None:
        return self.slices[0] if self.slices else None


# ---- hotels -------------------------------------------------------------
class GeoPoint(TravelCrewModel):
    latitude: float
    longitude: float


class HotelRoom(TravelCrewModel):
    name: str
    board: str | None = None
    occupancy: int | None = None
    beds: str | None = None


class CancellationPolicy(TravelCrewModel):
    free_cancellation: bool | None = None
    deadline: datetime | None = None
    penalty: OptionalMoney = None
    note: str | None = None


class HotelOffer(TravelCrewModel):
    """One stay, priced for the whole stay rather than per night.

    The nightly rate is kept, because travellers shop on it, but ``total_stay``
    is what ranking sorts on and what the budget is charged. A hotel that looks
    cheap per night and is not cheap for five nights with taxes must not win a
    "cheapest" sort.
    """

    offer_id: str
    meta: OfferMeta

    name: str
    area: str | None = None
    address: str | None = None
    coordinates: GeoPoint | None = None
    image_url: str | None = None

    star_rating: float | None = None
    review_score: float | None = None
    review_count: int | None = None

    room: HotelRoom | None = None
    check_in: date | None = None
    check_out: date | None = None
    nights: int = 1
    rooms: int = 1

    price_per_night: MoneyAmount = Field(default=Decimal(0))
    taxes: MoneyAmount = Field(default=Decimal(0))
    fees: MoneyAmount = Field(default=Decimal(0))
    total_stay: MoneyAmount = Field(default=Decimal(0))
    currency: str = "USD"

    breakfast_included: bool = False
    amenities: list[str] = Field(default_factory=list)
    cancellation: CancellationPolicy = Field(default_factory=CancellationPolicy)
    distance_to_centre_km: float | None = None
    # Distance to whatever this trip is actually built around, when known.
    distance_to_focus_km: float | None = None

    @model_validator(mode="after")
    def _default_total(self) -> HotelOffer:
        if self.total_stay == 0:
            room_total = self.price_per_night * self.nights * max(self.rooms, 1)
            object.__setattr__(self, "total_stay", room_total + self.taxes + self.fees)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def room_subtotal(self) -> Decimal:
        """The room before taxes and fees - the "$420" on the example card."""
        return self.price_per_night * self.nights * max(self.rooms, 1)


# ---- activities ---------------------------------------------------------
class ActivityOffer(TravelCrewModel):
    offer_id: str
    meta: OfferMeta

    name: str
    category: str | None = None
    summary: str | None = None
    image_url: str | None = None

    location: str | None = None
    coordinates: GeoPoint | None = None

    duration_minutes: int | None = None
    rating: float | None = None
    review_count: int | None = None

    price_per_person: MoneyAmount = Field(default=Decimal(0))
    total_price: MoneyAmount = Field(default=Decimal(0))
    currency: str = "USD"
    participants: int = 1

    # None means the provider does not publish availability, which is not the
    # same as "sold out" and must not be rendered as one.
    available: bool | None = None
    available_dates: list[date] = Field(default_factory=list)
    cancellation: CancellationPolicy = Field(default_factory=CancellationPolicy)

    @model_validator(mode="after")
    def _default_total(self) -> ActivityOffer:
        if self.total_price == 0 and self.participants:
            object.__setattr__(
                self, "total_price", self.price_per_person * self.participants
            )
        return self


__all__ = [
    "ActivityOffer",
    "Badge",
    "BaggageAllowance",
    "CabinClass",
    "CancellationPolicy",
    "DEFAULT_OFFER_TTL",
    "FareConditions",
    "FlightOffer",
    "FlightSegment",
    "FlightSlice",
    "GeoPoint",
    "HotelOffer",
    "HotelRoom",
    "Layover",
    "OfferKind",
    "OfferMeta",
    "PriceBreakdown",
    "SortMode",
]
