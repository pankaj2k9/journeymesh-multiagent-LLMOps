"""The provider contract.

These tests are written against the *Protocol*, not against the mock. Every
adapter added later - Amadeus, Duffel, a hotel bank - is added to the fixtures
here and has to satisfy the same assertions. That is the point of having a
contract at all: the guarantees business logic relies on are stated once and
checked for everybody.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.constants import PAYABLE_SOURCES, SOURCE_MOCK
from app.providers.activities.mock import MockActivityProvider
from app.providers.base import (
    ActivityProvider,
    FlightProvider,
    HotelProvider,
    OfferNotFound,
)
from app.providers.flights.mock import MockFlightProvider
from app.providers.hotels.mock import MockHotelProvider
from app.schemas.search import (
    ActivitySearchCriteria,
    FlightSearchCriteria,
    HotelSearchCriteria,
)

DEPART = date(2027, 6, 10)
RETURN = date(2027, 6, 17)


def flight_criteria(**overrides) -> FlightSearchCriteria:
    payload = {
        "origin": "Dhaka",
        "destination": "Barcelona",
        "departure_date": DEPART,
        "return_date": RETURN,
        "adults": 2,
        "children": 1,
        "child_ages": [7],
        "baggage": "checked",
    }
    payload.update(overrides)
    return FlightSearchCriteria.model_validate(payload)


def hotel_criteria(**overrides) -> HotelSearchCriteria:
    payload = {
        "destination": "Barcelona",
        "check_in": DEPART,
        "check_out": DEPART + timedelta(days=5),
        "adults": 2,
        "children": 1,
        "child_ages": [7],
    }
    payload.update(overrides)
    return HotelSearchCriteria.model_validate(payload)


# ---- structural conformance ---------------------------------------------
class TestProtocolConformance:
    def test_the_flight_adapter_satisfies_the_protocol(self) -> None:
        assert isinstance(MockFlightProvider(), FlightProvider)

    def test_the_hotel_adapter_satisfies_the_protocol(self) -> None:
        assert isinstance(MockHotelProvider(), HotelProvider)

    def test_the_activity_adapter_satisfies_the_protocol(self) -> None:
        assert isinstance(MockActivityProvider(), ActivityProvider)

    @pytest.mark.parametrize(
        "provider",
        [MockFlightProvider(), MockHotelProvider(), MockActivityProvider()],
        ids=["flights", "hotels", "activities"],
    )
    def test_every_provider_names_itself(self, provider) -> None:
        assert isinstance(provider.name, str) and provider.name


# ---- flights ------------------------------------------------------------
class TestFlightProviderContract:
    @pytest.fixture()
    def provider(self) -> MockFlightProvider:
        return MockFlightProvider()

    async def test_a_search_returns_normalised_offers(self, provider) -> None:
        offers = await provider.search_flights(flight_criteria())
        assert offers
        for offer in offers:
            assert offer.offer_id
            assert offer.meta.provider == provider.name
            assert offer.slices, "an itinerary with no legs is not an itinerary"
            assert offer.total_price > 0
            assert offer.currency == "USD"

    async def test_the_same_search_always_returns_the_same_offers(self, provider) -> None:
        """Determinism is what makes everything downstream testable."""
        first = await provider.search_flights(flight_criteria())
        second = await MockFlightProvider().search_flights(flight_criteria())
        assert [offer.offer_id for offer in first] == [offer.offer_id for offer in second]
        assert [offer.total_price for offer in first] == [
            offer.total_price for offer in second
        ]

    async def test_a_different_search_returns_different_offers(self, provider) -> None:
        here = await provider.search_flights(flight_criteria())
        elsewhere = await provider.search_flights(flight_criteria(destination="Tokyo"))
        assert {offer.offer_id for offer in here} != {offer.offer_id for offer in elsewhere}

    async def test_the_price_breakdown_adds_up_to_what_is_charged(self, provider) -> None:
        for offer in await provider.search_flights(flight_criteria()):
            price = offer.price_per_traveler
            assert price.total == price.base_fare + price.taxes + price.fees + price.baggage_fee

    async def test_a_round_trip_has_two_slices(self, provider) -> None:
        offers = await provider.search_flights(flight_criteria())
        assert all(len(offer.slices) == 2 for offer in offers)

    async def test_a_one_way_has_one(self, provider) -> None:
        offers = await provider.search_flights(flight_criteria(return_date=None))
        assert all(len(offer.slices) == 1 for offer in offers)

    async def test_everything_is_labelled_mock(self, provider) -> None:
        """The label the budget engine relies on to refuse a commitment."""
        for offer in await provider.search_flights(flight_criteria()):
            assert offer.meta.source == SOURCE_MOCK
            assert offer.meta.source not in PAYABLE_SOURCES
            assert offer.meta.payable is False

    async def test_every_offer_carries_an_expiry(self, provider) -> None:
        for offer in await provider.search_flights(flight_criteria()):
            assert offer.meta.expires_at is not None
            assert not offer.meta.is_expired()

    async def test_children_are_cheaper_than_adults(self, provider) -> None:
        offers = await provider.search_flights(flight_criteria())
        for offer in offers:
            naive = offer.price_per_traveler.total * offer.travelers
            assert offer.total_price < naive, "a child priced as an adult is a bug"

    # ---- criteria are honoured ------------------------------------------
    async def test_max_stops_is_respected(self, provider) -> None:
        for limit in (0, 1):
            offers = await provider.search_flights(flight_criteria(max_stops=limit))
            assert offers
            assert all(offer.stops <= limit for offer in offers)

    async def test_an_excluded_airline_never_appears(self, provider) -> None:
        offers = await provider.search_flights(
            flight_criteria(excluded_airlines=["TK", "EK"])
        )
        assert offers
        for offer in offers:
            assert "TK" not in offer.airline_codes
            assert "EK" not in offer.airline_codes

    async def test_excluding_everything_returns_nothing_rather_than_failing(
        self, provider
    ) -> None:
        offers = await provider.search_flights(
            flight_criteria(
                excluded_airlines=["TK", "EK", "QR", "SQ", "EY", "BG", "6E", "MH"]
            )
        )
        assert offers == []

    async def test_a_price_ceiling_filters(self, provider) -> None:
        unlimited = await provider.search_flights(flight_criteria())
        ceiling = min(offer.total_price for offer in unlimited)
        limited = await provider.search_flights(flight_criteria(max_total_price=ceiling))
        assert limited
        assert all(offer.total_price <= ceiling for offer in limited)

    async def test_a_cabin_upgrade_costs_more(self, provider) -> None:
        economy = await provider.search_flights(flight_criteria(cabin_class="economy"))
        business = await provider.search_flights(flight_criteria(cabin_class="business"))
        assert min(o.total_price for o in business) > min(o.total_price for o in economy)
        assert all(offer.cabin == "business" for offer in business)

    async def test_asking_for_a_bag_adds_a_fee_only_where_it_is_not_included(
        self, provider
    ) -> None:
        offers = await provider.search_flights(flight_criteria(baggage="checked"))
        for offer in offers:
            if offer.baggage.checked_included:
                assert offer.price_per_traveler.baggage_fee == 0
            else:
                assert offer.price_per_traveler.baggage_fee > 0

    async def test_a_departure_window_is_respected(self, provider) -> None:
        offers = await provider.search_flights(
            flight_criteria(earliest_departure_hour=5, latest_departure_hour=11)
        )
        for offer in offers:
            hour = offer.outbound.departure_time.hour
            assert 5 <= hour <= 11

    # ---- single offer ----------------------------------------------------
    async def test_an_offer_can_be_read_back(self, provider) -> None:
        offers = await provider.search_flights(flight_criteria())
        again = await provider.get_offer(offers[0].offer_id)
        assert again.offer_id == offers[0].offer_id
        assert again.total_price == offers[0].total_price

    async def test_an_unknown_offer_is_a_404_not_a_crash(self, provider) -> None:
        with pytest.raises(OfferNotFound):
            await provider.get_offer("nope")

    async def test_revalidation_reports_the_same_or_a_changed_price(self, provider) -> None:
        offers = await provider.search_flights(flight_criteria())
        for offer in offers:
            check = await provider.revalidate_price(offer.offer_id)
            assert check.offer_id == offer.offer_id
            assert check.currency == offer.currency
            assert check.old_total == offer.total_price
            if check.changed:
                assert check.new_total != check.old_total

    async def test_revalidation_is_deterministic_for_one_offer(self, provider) -> None:
        offer = (await provider.search_flights(flight_criteria()))[0]
        first = await provider.revalidate_price(offer.offer_id)
        second = await provider.revalidate_price(offer.offer_id)
        assert (first.new_total, first.still_available) == (
            second.new_total,
            second.still_available,
        )

    async def test_the_price_change_branch_is_reachable_offline(self, provider) -> None:
        """Somewhere in a reasonable number of searches, a price must move.

        Without this the price-change path would only ever be exercised against
        a live provider, which is to say in production.
        """
        seen_change = False
        for day in range(1, 40):
            criteria = flight_criteria(
                departure_date=DEPART + timedelta(days=day),
                return_date=RETURN + timedelta(days=day),
            )
            for offer in await provider.search_flights(criteria):
                check = await provider.revalidate_price(offer.offer_id)
                if check.changed or not check.still_available:
                    seen_change = True
                    break
            if seen_change:
                break
        assert seen_change

    # ---- booking ---------------------------------------------------------
    async def test_booking_returns_a_provider_reference(self, provider) -> None:
        offer = (await provider.search_flights(flight_criteria()))[0]
        booking = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="key-1"
        )
        assert booking["booking_reference"]
        assert booking["status"] == "CONFIRMED"
        assert booking["provider"] == provider.name

    async def test_the_same_idempotency_key_never_books_twice(self, provider) -> None:
        """The guarantee that makes a retried request safe."""
        offer = (await provider.search_flights(flight_criteria()))[0]
        first = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="same-key"
        )
        second = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="same-key"
        )
        assert first["booking_reference"] == second["booking_reference"]

    async def test_different_keys_book_separately(self, provider) -> None:
        offer = (await provider.search_flights(flight_criteria()))[0]
        first = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="key-a"
        )
        second = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="key-b"
        )
        assert first["booking_reference"] != second["booking_reference"]

    async def test_a_booking_can_be_read_back_and_cancelled(self, provider) -> None:
        offer = (await provider.search_flights(flight_criteria()))[0]
        booking = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="key-c"
        )
        reference = booking["booking_reference"]

        assert (await provider.get_booking(reference))["status"] == "CONFIRMED"
        cancelled = await provider.cancel_booking(reference)
        assert cancelled["status"] == "CANCELLED"
        assert (await provider.get_booking(reference))["status"] == "CANCELLED"


# ---- hotels -------------------------------------------------------------
class TestHotelProviderContract:
    @pytest.fixture()
    def provider(self) -> MockHotelProvider:
        return MockHotelProvider()

    async def test_a_search_returns_priced_stays(self, provider) -> None:
        offers = await provider.search_hotels(hotel_criteria())
        assert offers
        for offer in offers:
            assert offer.name
            assert offer.nights == 5
            assert offer.total_stay > 0
            assert offer.meta.source == SOURCE_MOCK

    async def test_the_stay_total_includes_taxes_and_fees(self, provider) -> None:
        for offer in await provider.search_hotels(hotel_criteria()):
            assert offer.total_stay == offer.room_subtotal + offer.taxes + offer.fees
            assert offer.total_stay > offer.room_subtotal, "taxes are never zero here"

    async def test_the_nightly_rate_alone_understates_the_stay(self, provider) -> None:
        for offer in await provider.search_hotels(hotel_criteria()):
            assert offer.total_stay > offer.price_per_night * offer.nights

    async def test_determinism(self, provider) -> None:
        first = await provider.search_hotels(hotel_criteria())
        second = await MockHotelProvider().search_hotels(hotel_criteria())
        assert [o.offer_id for o in first] == [o.offer_id for o in second]
        assert [o.total_stay for o in first] == [o.total_stay for o in second]

    async def test_a_star_rating_filter_is_respected(self, provider) -> None:
        offers = await provider.search_hotels(hotel_criteria(min_star_rating=4.0))
        assert all(offer.star_rating >= 4.0 for offer in offers)

    async def test_a_breakfast_filter_is_respected(self, provider) -> None:
        offers = await provider.search_hotels(hotel_criteria(breakfast_required=True))
        assert all(offer.breakfast_included for offer in offers)

    async def test_a_free_cancellation_filter_is_respected(self, provider) -> None:
        offers = await provider.search_hotels(
            hotel_criteria(free_cancellation_required=True)
        )
        assert all(offer.cancellation.free_cancellation for offer in offers)

    async def test_a_stay_ceiling_filters_on_the_total_not_the_night(self, provider) -> None:
        everything = await provider.search_hotels(hotel_criteria())
        ceiling = min(offer.total_stay for offer in everything)
        limited = await provider.search_hotels(hotel_criteria(max_total_stay=ceiling))
        assert limited
        assert all(offer.total_stay <= ceiling for offer in limited)

    async def test_booking_is_idempotent(self, provider) -> None:
        offer = (await provider.search_hotels(hotel_criteria()))[0]
        first = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="hotel-key"
        )
        second = await provider.create_booking(
            offer.offer_id, travelers=[{"name": "A"}], idempotency_key="hotel-key"
        )
        assert first["booking_reference"] == second["booking_reference"]


# ---- activities ---------------------------------------------------------
class TestActivityProviderContract:
    @pytest.fixture()
    def provider(self) -> MockActivityProvider:
        return MockActivityProvider()

    async def test_a_search_returns_priced_activities(self, provider) -> None:
        offers = await provider.search_activities(
            ActivitySearchCriteria(destination="Barcelona", participants=3)
        )
        assert offers
        for offer in offers:
            assert offer.name and offer.category
            assert offer.total_price == offer.price_per_person * offer.participants

    async def test_a_category_filter_is_respected(self, provider) -> None:
        offers = await provider.search_activities(
            ActivitySearchCriteria(destination="Barcelona", categories=["food"])
        )
        assert offers
        assert all(offer.category == "food" for offer in offers)

    async def test_unknown_availability_is_none_not_false(self, provider) -> None:
        """"Unknown" must never render as "sold out"."""
        offers = await provider.search_activities(
            ActivitySearchCriteria(destination="Barcelona", participants=2)
        )
        assert any(offer.available is None for offer in offers)

    async def test_a_price_ceiling_filters(self, provider) -> None:
        offers = await provider.search_activities(
            ActivitySearchCriteria(
                destination="Barcelona", max_price_per_person=Decimal("40")
            )
        )
        assert all(offer.price_per_person <= Decimal("40") for offer in offers)
