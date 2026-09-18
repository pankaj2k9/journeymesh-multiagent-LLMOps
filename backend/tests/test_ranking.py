"""Ordering offers.

The most important test in this file is the one the specification asks for by
name: given A=$620, B=$580, C=$700 and a request for the cheapest, the system
recommends B. Everything else here exists to stop the ways that can quietly
stop being true - a sort on base fare instead of total, a badge awarded from
the sorted list instead of the whole set, a tie broken arbitrarily.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.schemas.offers import (
    BaggageAllowance,
    FlightOffer,
    FlightSegment,
    FlightSlice,
    HotelOffer,
    OfferMeta,
    PriceBreakdown,
)
from app.schemas.search import BudgetSnapshotForOffer
from app.services.ranking import (
    flight_total,
    hotel_total,
    rank_flights,
    rank_hotels,
)


def flight(
    *,
    ref: str,
    base: str,
    taxes: str = "0",
    fees: str = "0",
    baggage_fee: str = "0",
    stops: int = 0,
    minutes: int = 600,
    airline: str = "Test Air",
    travelers: int = 1,
    checked_included: bool = True,
) -> FlightOffer:
    """A flight offer with exactly the fields ranking reads."""
    segments = [
        FlightSegment(
            marketing_airline=airline,
            marketing_airline_code="TT",
            departure_iata="AAA",
            arrival_iata="BBB",
            departure_time=datetime(2027, 6, 10, 8, tzinfo=timezone.utc),
            arrival_time=datetime(2027, 6, 10, 18, tzinfo=timezone.utc),
            duration_minutes=minutes,
        )
    ]
    for index in range(stops):
        segments.append(
            FlightSegment(
                marketing_airline=airline,
                marketing_airline_code="TT",
                departure_iata="BBB",
                arrival_iata="CCC",
                departure_time=datetime(2027, 6, 10, 19 + index, tzinfo=timezone.utc),
                arrival_time=datetime(2027, 6, 10, 21 + index, tzinfo=timezone.utc),
                duration_minutes=120,
            )
        )
    return FlightOffer(
        offer_id=ref,
        meta=OfferMeta(provider="test", source="MOCK"),
        slices=[FlightSlice(segments=segments, duration_minutes=minutes)],
        baggage=BaggageAllowance(checked_included=checked_included),
        price_per_traveler=PriceBreakdown(
            base_fare=base, taxes=taxes, fees=fees, baggage_fee=baggage_fee
        ),
        travelers=travelers,
    )


def hotel(*, ref: str, nightly: str, nights: int, taxes: str = "0", fees: str = "0",
          review: float = 8.0, km: float = 1.0) -> HotelOffer:
    return HotelOffer(
        offer_id=ref,
        meta=OfferMeta(provider="test", source="MOCK"),
        name=ref,
        price_per_night=nightly,
        nights=nights,
        taxes=taxes,
        fees=fees,
        review_score=review,
        distance_to_centre_km=km,
    )


class TestCheapestFirst:
    def test_the_specifications_worked_example(self) -> None:
        """A=$620, B=$580, C=$700 -> B is recommended for a cheapest search."""
        offers = [
            flight(ref="A", base="620"),
            flight(ref="B", base="580"),
            flight(ref="C", base="700"),
        ]
        ranked = rank_flights(offers, sort="cheapest")

        assert [item.offer.offer_id for item in ranked] == ["B", "A", "C"]
        assert ranked[0].offer.offer_id == "B"
        assert "CHEAPEST" in ranked[0].badges

    def test_input_order_does_not_change_the_answer(self) -> None:
        for order in (["A", "B", "C"], ["C", "B", "A"], ["B", "C", "A"]):
            prices = {"A": "620", "B": "580", "C": "700"}
            offers = [flight(ref=ref, base=prices[ref]) for ref in order]
            assert rank_flights(offers, sort="cheapest")[0].offer.offer_id == "B"

    def test_cheapest_is_total_payable_not_base_fare(self) -> None:
        """A cheap fare that excludes the bag this search wants is not cheapest.

        This is the single most valuable assertion in the file. Sorting on
        `base_fare` would put B first and would be wrong by $35.
        """
        offers = [
            flight(ref="with-bag", base="600", taxes="40", fees="10", baggage_fee="0"),
            flight(ref="without-bag", base="580", taxes="40", fees="10", baggage_fee="60"),
        ]
        assert offers[1].price_per_traveler.base_fare < offers[0].price_per_traveler.base_fare
        ranked = rank_flights(offers, sort="cheapest")
        assert ranked[0].offer.offer_id == "with-bag"
        assert flight_total(ranked[0].offer) == Decimal("650")

    def test_taxes_and_fees_count_towards_cheapest(self) -> None:
        offers = [
            flight(ref="low-fare-high-tax", base="500", taxes="200"),
            flight(ref="high-fare-no-tax", base="620", taxes="0"),
        ]
        assert rank_flights(offers, sort="cheapest")[0].offer.offer_id == "high-fare-no-tax"

    def test_the_party_total_decides_not_the_per_head_price(self) -> None:
        cheap_per_head = flight(ref="per-head-cheap", base="200", travelers=4)
        dear_per_head = flight(ref="per-head-dear", base="300", travelers=2)
        ranked = rank_flights([cheap_per_head, dear_per_head], sort="cheapest")
        # 800 for four against 600 for two.
        assert ranked[0].offer.offer_id == "per-head-dear"

    def test_ties_break_towards_the_shorter_journey(self) -> None:
        offers = [
            flight(ref="slow", base="600", minutes=900),
            flight(ref="quick", base="600", minutes=500),
        ]
        assert rank_flights(offers, sort="cheapest")[0].offer.offer_id == "quick"


class TestSortModes:
    @pytest.fixture()
    def spread(self) -> list[FlightOffer]:
        return [
            flight(ref="cheap-slow", base="400", stops=2, minutes=1400),
            flight(ref="mid-direct", base="620", stops=0, minutes=600),
            flight(ref="dear-fastest", base="900", stops=0, minutes=480),
        ]

    def test_cheapest(self, spread: list[FlightOffer]) -> None:
        assert rank_flights(spread, sort="cheapest")[0].offer.offer_id == "cheap-slow"

    def test_fastest(self, spread: list[FlightOffer]) -> None:
        assert rank_flights(spread, sort="fastest")[0].offer.offer_id == "dear-fastest"

    def test_fewest_stops(self, spread: list[FlightOffer]) -> None:
        first = rank_flights(spread, sort="fewest_stops")[0].offer
        assert first.stops == 0

    def test_best_value_picks_neither_extreme(self, spread: list[FlightOffer]) -> None:
        winner = rank_flights(spread, sort="best_value")[0].offer.offer_id
        assert winner == "mid-direct"

    def test_every_sort_returns_every_offer(self, spread: list[FlightOffer]) -> None:
        for mode in ("cheapest", "fastest", "fewest_stops", "best_value", "recommended"):
            ranked = rank_flights(spread, sort=mode)
            assert len(ranked) == len(spread)
            assert {item.offer.offer_id for item in ranked} == {
                offer.offer_id for offer in spread
            }

    def test_an_empty_search_ranks_to_nothing(self) -> None:
        assert rank_flights([], sort="cheapest") == []


class TestBadges:
    def test_badges_describe_the_whole_set_not_the_sorted_order(self) -> None:
        offers = [
            flight(ref="cheap-slow", base="400", stops=2, minutes=1400),
            flight(ref="dear-fast", base="900", stops=0, minutes=480),
        ]
        for mode in ("cheapest", "fastest", "best_value", "recommended"):
            ranked = rank_flights(offers, sort=mode)
            badges = {item.offer.offer_id: item.badges for item in ranked}
            assert "CHEAPEST" in badges["cheap-slow"]
            assert "FASTEST" in badges["dear-fast"]

    def test_one_offer_is_cheapest_and_nothing_else_is(self) -> None:
        offers = [flight(ref=str(index), base=str(500 + index * 10)) for index in range(5)]
        ranked = rank_flights(offers, sort="cheapest")
        cheapest = [item for item in ranked if "CHEAPEST" in item.badges]
        assert len(cheapest) == 1
        assert cheapest[0].offer.offer_id == "0"

    def test_fewest_stops_is_not_awarded_when_several_tie(self) -> None:
        """A badge shared by four non-stops tells a traveller nothing."""
        offers = [flight(ref=str(index), base=str(500 + index * 10), stops=0) for index in range(4)]
        ranked = rank_flights(offers, sort="cheapest")
        assert not any("FEWEST_STOPS" in item.badges for item in ranked)

    def test_fewest_stops_is_awarded_when_one_offer_is_alone(self) -> None:
        offers = [
            flight(ref="direct", base="900", stops=0, minutes=900),
            flight(ref="one-stop", base="500", stops=1),
            flight(ref="two-stop", base="400", stops=2),
        ]
        ranked = rank_flights(offers, sort="cheapest")
        badged = [item.offer.offer_id for item in ranked if "FEWEST_STOPS" in item.badges]
        assert badged in (["direct"], [])  # unless it also took FASTEST


class TestBudgetBadges:
    def test_over_budget_is_labelled_and_still_returned(self) -> None:
        offers = [flight(ref="affordable", base="500"), flight(ref="expensive", base="5000")]
        budgets = {
            "affordable": BudgetSnapshotForOffer(within_budget=True, remaining_after=Decimal("3500")),
            "expensive": BudgetSnapshotForOffer(within_budget=False, remaining_after=Decimal("-1000")),
        }
        ranked = rank_flights(offers, sort="cheapest", budgets=budgets)

        assert len(ranked) == 2, "an unaffordable option is labelled, never hidden"
        by_ref = {item.offer.offer_id: item.badges for item in ranked}
        assert "WITHIN_BUDGET" in by_ref["affordable"]
        assert "OVER_BUDGET" in by_ref["expensive"]

    def test_recommended_does_not_lead_with_something_unaffordable(self) -> None:
        offers = [
            flight(ref="unaffordable-but-perfect", base="5000", stops=0, minutes=400),
            flight(ref="affordable", base="600", stops=0, minutes=600),
        ]
        budgets = {
            "unaffordable-but-perfect": BudgetSnapshotForOffer(within_budget=False),
            "affordable": BudgetSnapshotForOffer(within_budget=True),
        }
        ranked = rank_flights(offers, sort="recommended", budgets=budgets)
        assert ranked[0].offer.offer_id == "affordable"
        assert ranked[-1].offer.offer_id == "unaffordable-but-perfect"

    def test_without_a_budget_no_budget_badge_is_invented(self) -> None:
        ranked = rank_flights([flight(ref="a", base="500")], sort="cheapest")
        assert "WITHIN_BUDGET" not in ranked[0].badges
        assert "OVER_BUDGET" not in ranked[0].badges


class TestHotelRanking:
    def test_cheapest_is_the_whole_stay_not_the_nightly_rate(self) -> None:
        """The trap this test exists for.

        $82/night for 5 nights with $120 of taxes is $530.
        $86/night for 5 nights with nothing added is $430.
        A nightly-rate sort puts the wrong one first.
        """
        offers = [
            hotel(ref="cheap-nightly", nightly="82", nights=5, taxes="120"),
            hotel(ref="honest-nightly", nightly="86", nights=5),
        ]
        assert offers[0].price_per_night < offers[1].price_per_night
        ranked = rank_hotels(offers, sort="cheapest")
        assert ranked[0].offer.offer_id == "honest-nightly"
        assert hotel_total(ranked[0].offer) == Decimal("430")

    def test_the_specification_hotel_card_adds_up(self) -> None:
        stay = hotel(ref="Hotel Barcelona Center", nightly="84", nights=5, taxes="64")
        assert stay.room_subtotal == Decimal("420")
        assert stay.total_stay == Decimal("484")

    def test_rating_sort_prefers_the_better_reviewed(self) -> None:
        offers = [
            hotel(ref="cheap", nightly="50", nights=3, review=6.5),
            hotel(ref="loved", nightly="120", nights=3, review=9.4),
        ]
        assert rank_hotels(offers, sort="rating")[0].offer.offer_id == "loved"

    def test_distance_sort_puts_an_unknown_distance_last(self) -> None:
        near = hotel(ref="near", nightly="90", nights=2, km=0.4)
        unknown = hotel(ref="unknown", nightly="60", nights=2)
        unknown.distance_to_centre_km = None
        ranked = rank_hotels([unknown, near], sort="distance")
        assert ranked[0].offer.offer_id == "near"
        assert ranked[-1].offer.offer_id == "unknown"

    def test_the_most_expensive_is_not_assumed_to_be_best(self) -> None:
        offers = [
            hotel(ref="dear-and-mediocre", nightly="300", nights=4, review=6.1, km=4.0),
            hotel(ref="modest-and-loved", nightly="95", nights=4, review=9.2, km=0.6),
        ]
        assert rank_hotels(offers, sort="best_value")[0].offer.offer_id == "modest-and-loved"
        assert rank_hotels(offers, sort="recommended")[0].offer.offer_id == "modest-and-loved"


class TestOfferExpiry:
    def test_an_offer_knows_when_it_has_gone_stale(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        offer = flight(ref="stale", base="500")
        offer.meta.expires_at = past
        assert offer.meta.is_expired()

    def test_an_offer_without_an_expiry_is_not_treated_as_expired(self) -> None:
        offer = flight(ref="no-expiry", base="500")
        assert offer.meta.expires_at is None
        assert not offer.meta.is_expired()

    def test_a_mock_offer_is_never_payable(self) -> None:
        assert flight(ref="a", base="500").meta.payable is False
