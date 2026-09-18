"""The offline activity provider.

Shaped so that a Viator-style adapter drops in beside it without anything
above changing: a product with a category, a duration, a per-person price, a
cancellation policy and an availability that may legitimately be unknown.

``available`` is tri-state for that last reason. Many activity providers do not
publish live availability, and rendering "unknown" as "sold out" would remove a
bookable experience from a traveller's plan on no evidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.core.constants import SOURCE_MOCK
from app.providers.base import OfferNotFound, PriceCheck
from app.providers.seeding import generator, jitter
from app.schemas.offers import (
    DEFAULT_OFFER_TTL,
    ActivityOffer,
    CancellationPolicy,
    GeoPoint,
    OfferMeta,
)
from app.schemas.search import ActivitySearchCriteria
from app.services.money import quantize, to_decimal

PROVIDER_NAME = "mock_activities"

# (category, template, typical per-person price, minutes)
_CATALOGUE: tuple[tuple[str, str, str, int], ...] = (
    ("culture", "{city} Old Town walking tour", "24", 150),
    ("culture", "{city} museum pass with skip-the-line entry", "38", 180),
    ("food", "{city} street food evening tour", "56", 210),
    ("food", "Market visit and cooking class in {city}", "78", 240),
    ("nature", "Day trip from {city} to the coast", "92", 480),
    ("nature", "Sunrise hike near {city}", "34", 300),
    ("history", "{city} historic quarter guided tour", "29", 120),
    ("photography", "{city} photography walk at golden hour", "45", 150),
    ("nightlife", "{city} live music and tapas crawl", "61", 195),
    ("family_activities", "{city} family science centre entry", "19", 180),
    ("shopping", "{city} artisan district guided shopping walk", "22", 120),
    ("beaches", "Catamaran afternoon from {city}", "74", 240),
)


class MockActivityProvider:
    name = PROVIDER_NAME

    def __init__(self) -> None:
        self._offers: dict[str, ActivityOffer] = {}
        self._bookings: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}

    async def search_activities(
        self, criteria: ActivitySearchCriteria
    ) -> list[ActivityOffer]:
        rng = generator(PROVIDER_NAME, criteria.cache_key())
        city = criteria.destination.strip().title()

        wanted = set(criteria.categories)
        catalogue = [
            entry for entry in _CATALOGUE if not wanted or entry[0] in wanted
        ]

        offers: list[ActivityOffer] = []
        for index, (category, template, base, minutes) in enumerate(catalogue):
            price = quantize(jitter(rng, base, 0.12), Decimal("0.01"))
            if criteria.max_price_per_person is not None:
                if price > to_decimal(criteria.max_price_per_person):
                    continue

            retrieved = datetime.now(timezone.utc)
            free_cancellation = bool(rng.random() < 0.7)
            # A third of products publish no availability at all.
            published = rng.random() > 0.33

            offer = ActivityOffer(
                offer_id=f"{PROVIDER_NAME}:{uuid.uuid5(uuid.NAMESPACE_URL, criteria.cache_key() + str(index))}",
                meta=OfferMeta(
                    provider=self.name,
                    source=SOURCE_MOCK,
                    retrieved_at=retrieved,
                    expires_at=retrieved + DEFAULT_OFFER_TTL,
                    provider_offer_id=f"A{index}",
                ),
                name=template.format(city=city),
                category=category,
                summary=f"A {minutes // 60}h {category.replace('_', ' ')} experience in {city}.",
                location=city,
                coordinates=GeoPoint(
                    latitude=round(rng.uniform(-60, 60), 5),
                    longitude=round(rng.uniform(-170, 170), 5),
                ),
                duration_minutes=minutes,
                rating=round(rng.uniform(3.8, 5.0), 1),
                review_count=rng.randint(24, 3100),
                price_per_person=price,
                participants=criteria.participants,
                currency=criteria.currency,
                available=bool(rng.random() < 0.85) if published else None,
                cancellation=CancellationPolicy(
                    free_cancellation=free_cancellation,
                    deadline=retrieved + timedelta(days=1) if free_cancellation else None,
                    note="Free cancellation up to 24h before"
                    if free_cancellation
                    else "Non-refundable",
                ),
            )
            offers.append(offer)
            self._offers[offer.offer_id] = offer
        return offers

    async def get_offer(self, offer_id: str) -> ActivityOffer:
        offer = self._offers.get(offer_id)
        if offer is None:
            raise OfferNotFound(f"offer {offer_id} is not held by {self.name}")
        return offer

    async def revalidate_price(self, offer_id: str) -> PriceCheck:
        offer = await self.get_offer(offer_id)
        total = to_decimal(offer.total_price)
        return PriceCheck(
            offer_id=offer_id,
            still_available=offer.available is not False,
            old_total=total,
            new_total=total,
            currency=offer.currency,
            checked_at=datetime.now(timezone.utc),
        )

    async def create_booking(
        self, offer_id: str, *, travelers: list[dict[str, Any]], idempotency_key: str
    ) -> dict[str, Any]:
        if idempotency_key in self._idempotency:
            return self._bookings[self._idempotency[idempotency_key]]

        offer = await self.get_offer(offer_id)
        rng = generator(PROVIDER_NAME, "booking", idempotency_key)
        reference = "A" + "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=7))
        booking = {
            "booking_reference": reference,
            "provider": self.name,
            "offer_id": offer_id,
            "status": "CONFIRMED",
            "total_amount": str(offer.total_price),
            "currency": offer.currency,
            "activity_name": offer.name,
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
