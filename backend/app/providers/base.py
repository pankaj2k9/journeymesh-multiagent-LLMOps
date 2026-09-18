"""The travel provider contract.

One Protocol per domain, and every implementation - the offline mock, Amadeus,
Duffel, whatever comes next - satisfies the same one. Business logic above this
line never learns which provider answered; it reads a ``FlightOffer`` and a
``ProviderNote`` and that is all there is.

The booking half of the contract is declared here from the start even though
Phase 4 implements it. Designing ``search`` without ``revalidate_price`` beside
it is how a system ends up with a search result that cannot be re-priced, and
re-pricing before payment is not optional.

Every method may raise ``ProviderUnavailable``. Nothing above catches a bare
``Exception`` from an adapter: the registry converts a failure into a note and
a fallback, so one provider being down degrades a search rather than ending it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.exceptions import TravelCrewError
from app.schemas.offers import ActivityOffer, FlightOffer, HotelOffer
from app.schemas.search import (
    ActivitySearchCriteria,
    FlightSearchCriteria,
    HotelSearchCriteria,
    ProviderNote,
)


class ProviderUnavailable(TravelCrewError):
    """The provider could not be reached, or answered with something unusable.

    Deliberately not a 500. A provider outage is an expected condition in this
    system: the search still returns, labelled, from whatever else answered.
    """

    status_code = 502
    code = "provider_unavailable"
    safe_message = "A travel data provider is currently unavailable."


class OfferExpired(TravelCrewError):
    status_code = 409
    code = "offer_expired"
    safe_message = "That offer has expired. Search again for a current price."


class OfferNotFound(TravelCrewError):
    status_code = 404
    code = "offer_not_found"
    safe_message = "That offer could not be found."


@dataclass(frozen=True)
class PriceCheck:
    """The result of re-pricing an offer immediately before booking.

    ``changed`` is the field the booking flow branches on, and it is computed
    from the amounts rather than trusted from the provider, because "the price
    is the same" is exactly the claim that must not be taken on faith.
    """

    offer_id: str
    still_available: bool
    old_total: Any
    new_total: Any
    currency: str
    checked_at: Any
    note: str | None = None

    @property
    def changed(self) -> bool:
        return self.old_total != self.new_total


@dataclass
class SearchOutcome:
    """What one provider returned, with how it went attached.

    Offers and the note travel together on purpose. A caller cannot render the
    offers while forgetting to say they came from the offline mock, because
    there is only one object and the note is on it.
    """

    offers: list[Any] = field(default_factory=list)
    note: ProviderNote | None = None


@runtime_checkable
class FlightProvider(Protocol):
    """What every flight source must be able to do."""

    #: Stable identifier written onto every offer and every provider call row.
    name: str

    async def search_flights(self, criteria: FlightSearchCriteria) -> list[FlightOffer]:
        """Find itineraries matching these criteria.

        Returning an empty list means "nothing matched", which is an answer.
        Raising ``ProviderUnavailable`` means "I could not tell you", which is
        not - and the two must never be conflated, because an empty result
        renders as "no flights on this route" to a traveller.
        """
        ...

    async def get_offer(self, offer_id: str) -> FlightOffer:
        """Re-read one offer by its identifier."""
        ...

    async def revalidate_price(self, offer_id: str) -> PriceCheck:
        """Confirm the price immediately before money moves."""
        ...

    async def create_booking(
        self, offer_id: str, *, travelers: list[dict[str, Any]], idempotency_key: str
    ) -> dict[str, Any]:
        """Buy it.

        ``idempotency_key`` is part of the contract rather than an
        implementation detail: a retried request must never produce a second
        booking, and that guarantee has to hold at the provider boundary.
        """
        ...

    async def get_booking(self, booking_reference: str) -> dict[str, Any]:
        ...

    async def cancel_booking(self, booking_reference: str) -> dict[str, Any]:
        ...


@runtime_checkable
class HotelProvider(Protocol):
    name: str

    async def search_hotels(self, criteria: HotelSearchCriteria) -> list[HotelOffer]:
        ...

    async def get_offer(self, offer_id: str) -> HotelOffer:
        ...

    async def revalidate_price(self, offer_id: str) -> PriceCheck:
        ...

    async def create_booking(
        self, offer_id: str, *, travelers: list[dict[str, Any]], idempotency_key: str
    ) -> dict[str, Any]:
        ...

    async def get_booking(self, booking_reference: str) -> dict[str, Any]:
        ...

    async def cancel_booking(self, booking_reference: str) -> dict[str, Any]:
        ...


@runtime_checkable
class ActivityProvider(Protocol):
    name: str

    async def search_activities(
        self, criteria: ActivitySearchCriteria
    ) -> list[ActivityOffer]:
        ...

    async def get_offer(self, offer_id: str) -> ActivityOffer:
        ...

    async def revalidate_price(self, offer_id: str) -> PriceCheck:
        ...

    async def create_booking(
        self, offer_id: str, *, travelers: list[dict[str, Any]], idempotency_key: str
    ) -> dict[str, Any]:
        ...

    async def get_booking(self, booking_reference: str) -> dict[str, Any]:
        ...

    async def cancel_booking(self, booking_reference: str) -> dict[str, Any]:
        ...


__all__ = [
    "ActivityProvider",
    "FlightProvider",
    "HotelProvider",
    "OfferExpired",
    "OfferNotFound",
    "PriceCheck",
    "ProviderUnavailable",
    "SearchOutcome",
]
