"""The offline hotel provider.

Prices the whole stay, not the night. A nightly rate is what a traveller
shops on and a stay total is what they pay, and the gap between the two -
taxes, fees, a rate that only applies to part of the stay - is where a "cheap"
hotel stops being cheap. This adapter models that gap on purpose, so ranking
and the budget are exercised against it offline.

Everything is labelled ``MOCK``, which the budget engine refuses to treat as a
payable obligation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.core.constants import SOURCE_MOCK
from app.mcp.search import _AMENITY_POOL, _AREA_TEMPLATES, _PREFERENCE_NIGHTLY, _STYLE_NIGHTLY
from app.providers.base import OfferNotFound, PriceCheck
from app.providers.seeding import generator, jitter
from app.schemas.offers import (
    DEFAULT_OFFER_TTL,
    CancellationPolicy,
    GeoPoint,
    HotelOffer,
    HotelRoom,
    OfferMeta,
)
from app.schemas.search import HotelSearchCriteria
from app.services.money import quantize, to_decimal

PROVIDER_NAME = "mock_hotels"

_NAME_PREFIXES = (
    "Hotel",
    "The",
    "Casa",
    "Grand",
    "Park",
    "Riverside",
)
_NAME_SUFFIXES = (
    "Center",
    "Plaza",
    "Residence",
    "Boutique",
    "Suites",
    "Garden",
    "House",
)

_ROOM_TYPES = (
    ("Double room", 2, "1 double bed"),
    ("Twin room", 2, "2 single beds"),
    ("Family room", 4, "1 double and 2 single beds"),
    ("Studio apartment", 3, "1 double bed and a sofa bed"),
    ("Deluxe king room", 2, "1 king bed"),
)

# City tax per person per night, plus a one-off service fee on the stay. Both
# are the kind of charge that never appears on a nightly rate.
_CITY_TAX_PER_PERSON_NIGHT = Decimal("2.75")
_SERVICE_FEE_RATE = Decimal("0.035")

_RESULT_COUNT = 8


class MockHotelProvider:
    name = PROVIDER_NAME

    def __init__(self) -> None:
        self._offers: dict[str, HotelOffer] = {}
        self._bookings: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}

    async def search_hotels(self, criteria: HotelSearchCriteria) -> list[HotelOffer]:
        rng = generator(PROVIDER_NAME, criteria.cache_key())
        low, high = _nightly_band(criteria)

        offers: list[HotelOffer] = []
        for index in range(_RESULT_COUNT):
            offer = self._build(criteria, rng, index, low, high)
            if _matches(offer, criteria):
                offers.append(offer)
                self._offers[offer.offer_id] = offer
        return offers

    async def get_offer(self, offer_id: str) -> HotelOffer:
        offer = self._offers.get(offer_id)
        if offer is None:
            raise OfferNotFound(f"offer {offer_id} is not held by {self.name}")
        return offer

    async def revalidate_price(self, offer_id: str) -> PriceCheck:
        offer = await self.get_offer(offer_id)
        rng = generator(PROVIDER_NAME, "revalidate", offer_id)
        old_total = to_decimal(offer.total_stay)
        roll = rng.random()

        if roll < 0.12:
            new_total = quantize(old_total * to_decimal("1.08"), Decimal("0.01"))
            note = "the rate for these dates has increased"
        elif roll < 0.16:
            return PriceCheck(
                offer_id=offer_id,
                still_available=False,
                old_total=old_total,
                new_total=old_total,
                currency=offer.currency,
                checked_at=datetime.now(timezone.utc),
                note="this room is no longer available for these dates",
            )
        else:
            new_total, note = old_total, None

        return PriceCheck(
            offer_id=offer_id,
            still_available=True,
            old_total=old_total,
            new_total=new_total,
            currency=offer.currency,
            checked_at=datetime.now(timezone.utc),
            note=note,
        )

    async def create_booking(
        self, offer_id: str, *, travelers: list[dict[str, Any]], idempotency_key: str
    ) -> dict[str, Any]:
        if idempotency_key in self._idempotency:
            return self._bookings[self._idempotency[idempotency_key]]

        offer = await self.get_offer(offer_id)
        rng = generator(PROVIDER_NAME, "booking", idempotency_key)
        reference = "H" + "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=7))

        booking = {
            "booking_reference": reference,
            "provider": self.name,
            "offer_id": offer_id,
            "status": "CONFIRMED",
            "total_amount": str(offer.total_stay),
            "currency": offer.currency,
            "hotel_name": offer.name,
            "check_in": offer.check_in.isoformat() if offer.check_in else None,
            "check_out": offer.check_out.isoformat() if offer.check_out else None,
            "traveler_count": len(travelers),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": SOURCE_MOCK,
        }
        self._bookings[reference] = booking
        self._idempotency[idempotency_key] = reference
        return booking

    async def get_booking(self, booking_reference: str) -> dict[str, Any]:
        booking = self._bookings.get(booking_reference)
        if booking is None:
            raise OfferNotFound(f"booking {booking_reference} is not held by {self.name}")
        return booking

    async def cancel_booking(self, booking_reference: str) -> dict[str, Any]:
        booking = await self.get_booking(booking_reference)
        booking["status"] = "CANCELLED"
        booking["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        return booking

    # ---- construction ----------------------------------------------------
    def _build(
        self,
        criteria: HotelSearchCriteria,
        rng: Any,
        index: int,
        low: Decimal,
        high: Decimal,
    ) -> HotelOffer:
        nights = criteria.nights
        rooms = criteria.rooms

        # Spread the band across the result set so the list has a real cheap
        # end and a real expensive end rather than eight near-identical prices.
        position = Decimal(index) / Decimal(max(_RESULT_COUNT - 1, 1))
        nightly = quantize(jitter(rng, low + (high - low) * position, 0.08), Decimal("0.01"))

        area, area_note = _AREA_TEMPLATES[index % len(_AREA_TEMPLATES)]
        room_name, occupancy, beds = _ROOM_TYPES[index % len(_ROOM_TYPES)]

        room_subtotal = nightly * nights * rooms
        city_tax = quantize(
            _CITY_TAX_PER_PERSON_NIGHT * criteria.guests * nights, Decimal("0.01")
        )
        service_fee = quantize(room_subtotal * _SERVICE_FEE_RATE, Decimal("0.01"))

        star = round(2.5 + (float(position) * 2.5) + rng.uniform(-0.3, 0.3), 1)
        star = max(1.0, min(5.0, star))
        # Review score tracks stars loosely - an expensive hotel is not
        # automatically a better-reviewed one, which matters for "best value".
        review = round(min(9.6, max(6.0, star * 1.7 + rng.uniform(-0.9, 0.9))), 1)

        free_cancellation = bool(rng.random() < 0.65)
        breakfast = bool(rng.random() < 0.5)

        amenities = sorted(rng.sample(_AMENITY_POOL, k=rng.randint(3, 6)))
        if breakfast and "breakfast included" not in amenities:
            amenities.append("breakfast included")

        retrieved = datetime.now(timezone.utc)
        name = (
            f"{_NAME_PREFIXES[index % len(_NAME_PREFIXES)]} "
            f"{criteria.destination.strip().title()} "
            f"{_NAME_SUFFIXES[index % len(_NAME_SUFFIXES)]}"
        )

        return HotelOffer(
            offer_id=f"{PROVIDER_NAME}:{uuid.uuid5(uuid.NAMESPACE_URL, criteria.cache_key() + str(index))}",
            meta=OfferMeta(
                provider=self.name,
                source=SOURCE_MOCK,
                retrieved_at=retrieved,
                expires_at=retrieved + DEFAULT_OFFER_TTL,
                provider_offer_id=f"H{index}",
            ),
            name=name,
            area=f"{area} - {area_note}",
            coordinates=GeoPoint(
                latitude=round(rng.uniform(-60, 60), 5),
                longitude=round(rng.uniform(-170, 170), 5),
            ),
            star_rating=star,
            review_score=review,
            review_count=rng.randint(80, 4200),
            room=HotelRoom(
                name=room_name,
                board="Breakfast included" if breakfast else "Room only",
                occupancy=occupancy,
                beds=beds,
            ),
            check_in=criteria.check_in,
            check_out=criteria.check_out,
            nights=nights,
            rooms=rooms,
            price_per_night=nightly,
            taxes=city_tax,
            fees=service_fee,
            currency=criteria.currency,
            breakfast_included=breakfast,
            amenities=amenities,
            cancellation=CancellationPolicy(
                free_cancellation=free_cancellation,
                deadline=(
                    datetime.combine(criteria.check_in, datetime.min.time()).replace(
                        tzinfo=timezone.utc
                    )
                    - timedelta(days=2)
                    if free_cancellation
                    else None
                ),
                note="Free cancellation until 48h before check-in"
                if free_cancellation
                else "Non-refundable rate",
            ),
            distance_to_centre_km=round(0.3 + float(index) * 0.55 + rng.uniform(0, 0.4), 1),
        )


def _nightly_band(criteria: HotelSearchCriteria) -> tuple[Decimal, Decimal]:
    """Reuse the project's existing nightly-rate bands rather than a new table."""
    band = _PREFERENCE_NIGHTLY.get(criteria.accommodation_type)
    if band is None:
        band = _STYLE_NIGHTLY.get("comfort", (70.0, 130.0))
    return to_decimal(band[0]), to_decimal(band[1])


def _matches(offer: HotelOffer, criteria: HotelSearchCriteria) -> bool:
    if criteria.min_star_rating is not None and (offer.star_rating or 0) < criteria.min_star_rating:
        return False
    if criteria.min_review_score is not None and (offer.review_score or 0) < criteria.min_review_score:
        return False
    if criteria.breakfast_required and not offer.breakfast_included:
        return False
    if criteria.free_cancellation_required and not offer.cancellation.free_cancellation:
        return False
    if criteria.max_distance_km is not None:
        if (offer.distance_to_centre_km or 0) > criteria.max_distance_km:
            return False
    if criteria.max_total_stay is not None:
        if to_decimal(offer.total_stay) > to_decimal(criteria.max_total_stay):
            return False
    return True
