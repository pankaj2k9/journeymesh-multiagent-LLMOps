"""The budget engine.

Money is the part of this application that must not be approximately right, so
these tests are about arithmetic, provenance and the ledger's append-only
promise rather than about HTTP.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.constants import (
    CATEGORY_ACCOMMODATION,
    CATEGORY_ACTIVITY,
    CATEGORY_FLIGHT,
    CATEGORY_LOCAL_TRANSPORT,
    ITEM_BOOKED,
    ITEM_ESTIMATED,
    ITEM_PAID,
    ITEM_SELECTED,
    SOURCE_ESTIMATE,
    SOURCE_LIVE,
    SOURCE_MOCK,
)
from app.core.exceptions import (
    BudgetItemNotFound,
    CurrencyConflict,
    InvalidBudgetTransition,
    TripNotFound,
)
from app.db.models import Trip
from app.services.budget_engine import BudgetEngine


def make_trip(session: Session, *, budget: float | None = 4000.0, currency: str = "USD") -> Trip:
    trip = Trip(
        user_query="Plan a trip from Dhaka to Barcelona",
        origin="Dhaka",
        destination="Barcelona",
        travelers=3,
        budget=budget,
        currency=currency,
    )
    session.add(trip)
    session.flush()
    return trip


@pytest.fixture()
def engine(db_session: Session) -> BudgetEngine:
    return BudgetEngine(db_session)


class TestLifecycle:
    def test_a_budget_is_created_on_first_use(self, db_session: Session, engine: BudgetEngine) -> None:
        trip = make_trip(db_session)
        snapshot = engine.snapshot(trip.id)
        assert snapshot.trip_id == trip.id
        assert snapshot.total_budget == Decimal("4000.00")
        assert snapshot.currency == "USD"

    def test_the_planning_budget_carries_across_from_the_trip(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session, budget=2500.0)
        assert engine.snapshot(trip.id).total_budget == Decimal("2500.00")

    def test_a_trip_with_no_budget_reports_no_budget_set(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session, budget=None)
        snapshot = engine.snapshot(trip.id)
        assert snapshot.total_budget is None
        assert snapshot.remaining_budget is None
        assert snapshot.verdict == "no_budget_set"

    def test_an_unknown_trip_is_a_404_not_a_new_budget(self, engine: BudgetEngine) -> None:
        with pytest.raises(TripNotFound):
            engine.snapshot("does-not-exist")

    def test_a_default_reserve_is_five_percent(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session, budget=4000.0)
        assert engine.snapshot(trip.id).emergency_reserve == Decimal("200.00")


class TestTotals:
    def test_the_worked_example_from_the_specification(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        """Total 4000, flights 1820, hotel 920, activities 340, transport 220."""
        trip = make_trip(db_session)
        engine.set_budget(trip.id, emergency_reserve=0)

        for category, amount, label in (
            (CATEGORY_FLIGHT, "1820", "Turkish Airlines DAC-BCN"),
            (CATEGORY_ACCOMMODATION, "920", "Hotel Barcelona Center"),
            (CATEGORY_ACTIVITY, "340", "Sagrada Familia + Park Guell"),
            (CATEGORY_LOCAL_TRANSPORT, "220", "Metro passes and transfers"),
        ):
            _, budget = engine.add_item(
                trip.id, category=category, amount=amount, label=label, state=ITEM_SELECTED
            )

        assert budget.planned_cost == Decimal("3300.00")
        assert budget.allocated_cost == Decimal("3300.00")
        assert budget.remaining_budget == Decimal("700.00")
        assert budget.categories.flight_cost == Decimal("1820.00")
        assert budget.categories.accommodation_cost == Decimal("920.00")
        assert budget.verdict == "within_budget"

    def test_commitment_states_are_kept_apart(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, emergency_reserve=0)
        engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1000",
            state=ITEM_BOOKED, source=SOURCE_LIVE,
        )
        engine.add_item(trip.id, category=CATEGORY_ACCOMMODATION, amount="500", state=ITEM_SELECTED)
        budget = engine.add_item(
            trip.id, category=CATEGORY_ACTIVITY, amount="200", state=ITEM_ESTIMATED
        )[1]

        assert budget.committed_cost == Decimal("1000.00")
        assert budget.planned_cost == Decimal("500.00")
        assert budget.estimated_cost == Decimal("200.00")
        assert budget.allocated_cost == Decimal("1700.00")
        assert budget.remaining_budget == Decimal("2300.00")

    def test_the_reserve_is_held_back_from_remaining(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, total_budget="4000", emergency_reserve="400")
        budget = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1000", state=ITEM_SELECTED
        )[1]
        assert budget.remaining_budget == Decimal("2600.00")

    def test_overspending_is_reported_not_clamped(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, emergency_reserve=0)
        budget = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="4300", state=ITEM_SELECTED
        )[1]
        assert budget.remaining_budget == Decimal("-300.00")
        assert budget.verdict == "over_budget"

    def test_near_limit_fires_at_ninety_two_percent(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, emergency_reserve=0)
        budget = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="3680", state=ITEM_SELECTED
        )[1]
        assert budget.verdict == "near_limit"

    def test_cents_do_not_drift_over_many_lines(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, total_budget="100", emergency_reserve=0)
        for _ in range(100):
            budget = engine.add_item(
                trip.id, category=CATEGORY_ACTIVITY, amount="0.01", state=ITEM_ESTIMATED
            )[1]
        assert budget.estimated_cost == Decimal("1.00")
        assert budget.remaining_budget == Decimal("99.00")


class TestLedgerIsAppendOnly:
    def test_a_reversal_is_a_new_negative_line(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        item, _ = engine.add_item(
            trip.id, category=CATEGORY_ACTIVITY, amount="80",
            label="Museum", state=ITEM_SELECTED,
        )
        reversal, budget = engine.reverse_item(trip.id, item.id)

        assert reversal.amount == Decimal("-80.0000")
        assert reversal.reverses_id == item.id
        assert budget.categories.activity_cost == Decimal("0.00")

        # The original is still there - that is the point of an audit trail.
        lines, total = engine.ledger(trip.id)
        assert total == 2
        assert {line.id for line in lines} == {item.id, reversal.id}

    def test_a_line_cannot_be_reversed_twice(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        item, _ = engine.add_item(
            trip.id, category=CATEGORY_ACTIVITY, amount="80", state=ITEM_SELECTED
        )
        engine.reverse_item(trip.id, item.id)
        with pytest.raises(InvalidBudgetTransition):
            engine.reverse_item(trip.id, item.id)

    def test_a_reversal_cannot_itself_be_reversed(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        item, _ = engine.add_item(
            trip.id, category=CATEGORY_ACTIVITY, amount="80", state=ITEM_SELECTED
        )
        reversal, _ = engine.reverse_item(trip.id, item.id)
        with pytest.raises(InvalidBudgetTransition):
            engine.reverse_item(trip.id, reversal.id)

    def test_reversing_an_unknown_line_is_a_404(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        with pytest.raises(BudgetItemNotFound):
            engine.reverse_item(trip.id, "no-such-line")

    def test_choosing_a_second_flight_replaces_the_first(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, emergency_reserve=0)
        engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1836",
            state=ITEM_SELECTED, source_type="flight_offer", source_id="offer-a",
        )
        _, budget = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1740",
            state=ITEM_SELECTED, source_type="flight_offer", source_id="offer-b",
            replaces_source_type="flight_offer",
        )
        # Not 3576: the first selection was reversed, not added to.
        assert budget.categories.flight_cost == Decimal("1740.00")
        assert budget.remaining_budget == Decimal("2260.00")


class TestStateTransitions:
    def test_the_ladder_runs_one_way(self, db_session: Session, engine: BudgetEngine) -> None:
        trip = make_trip(db_session)
        item, _ = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1836", state=ITEM_ESTIMATED
        )
        item, _ = engine.promote(trip.id, item.id, to_state=ITEM_SELECTED)
        assert item.state == ITEM_SELECTED
        item, _ = engine.promote(trip.id, item.id, to_state=ITEM_BOOKED, source=SOURCE_LIVE)
        assert item.state == ITEM_BOOKED
        item, budget = engine.promote(trip.id, item.id, to_state=ITEM_PAID)
        assert item.state == ITEM_PAID
        assert budget.committed_cost == Decimal("1836.00")

    def test_money_never_walks_backwards(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        item, _ = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1836",
            state=ITEM_BOOKED, source=SOURCE_LIVE,
        )
        with pytest.raises(InvalidBudgetTransition):
            engine.promote(trip.id, item.id, to_state=ITEM_SELECTED)

    def test_skipping_a_rung_is_refused(self, db_session: Session, engine: BudgetEngine) -> None:
        trip = make_trip(db_session)
        item, _ = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1836", state=ITEM_ESTIMATED
        )
        with pytest.raises(InvalidBudgetTransition):
            engine.promote(trip.id, item.id, to_state=ITEM_BOOKED, source=SOURCE_LIVE)


class TestProvenance:
    def test_an_estimate_can_never_be_booked(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        with pytest.raises(InvalidBudgetTransition):
            engine.add_item(
                trip.id, category=CATEGORY_FLIGHT, amount="1836",
                state=ITEM_BOOKED, source=SOURCE_ESTIMATE,
            )

    def test_a_mock_price_can_never_be_booked(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        with pytest.raises(InvalidBudgetTransition):
            engine.add_item(
                trip.id, category=CATEGORY_FLIGHT, amount="1836",
                state=ITEM_PAID, source=SOURCE_MOCK,
            )

    def test_promotion_to_booked_also_requires_a_payable_source(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        item, _ = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1836",
            state=ITEM_SELECTED, source=SOURCE_MOCK,
        )
        with pytest.raises(InvalidBudgetTransition):
            engine.promote(trip.id, item.id, to_state=ITEM_BOOKED)

    def test_a_live_price_may_be_booked(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        item, budget = engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1836",
            state=ITEM_BOOKED, source=SOURCE_LIVE,
        )
        assert item.source == SOURCE_LIVE
        assert budget.committed_cost == Decimal("1836.00")


class TestCurrencyDiscipline:
    def test_a_line_in_another_currency_is_refused(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session, currency="USD")
        with pytest.raises(CurrencyConflict):
            engine.add_item(
                trip.id, category=CATEGORY_FLIGHT, amount="1836", currency="EUR"
            )

    def test_a_budget_cannot_be_re_denominated_once_it_holds_money(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session, currency="USD")
        engine.add_item(trip.id, category=CATEGORY_FLIGHT, amount="1836")
        with pytest.raises(CurrencyConflict):
            engine.ensure(trip.id, currency="EUR")


class TestImpact:
    def test_the_worked_example_from_the_flight_card(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        """$625/traveller x 3 against a $4,000 budget leaves $2,125."""
        trip = make_trip(db_session)
        engine.set_budget(trip.id, total_budget="4000", emergency_reserve=0)

        impact = engine.impact_of(
            trip.id, amount="1875", travelers=3,
            label="Turkish Airlines DAC-BCN", source=SOURCE_LIVE,
        )
        assert impact.item_total == Decimal("1875.00")
        assert impact.per_traveler == Decimal("625.00")
        assert impact.remaining_before == Decimal("4000.00")
        assert impact.remaining_after == Decimal("2125.00")
        assert impact.percentage_of_budget == pytest.approx(46.9, abs=0.1)
        assert impact.within_budget is True
        assert impact.payable is True

    def test_impact_subtracts_what_is_already_committed(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, total_budget="4000", emergency_reserve=0)
        engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1820",
            state=ITEM_BOOKED, source=SOURCE_LIVE,
        )
        impact = engine.impact_of(
            trip.id, amount="920", travelers=3, source=SOURCE_LIVE
        )
        assert impact.committed_before == Decimal("1820.00")
        assert impact.remaining_after == Decimal("1260.00")

    def test_impact_nets_out_the_offer_it_would_replace(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, total_budget="4000", emergency_reserve=0)
        engine.add_item(
            trip.id, category=CATEGORY_FLIGHT, amount="1875",
            state=ITEM_SELECTED, source_type="flight_offer", source_id="a",
        )
        impact = engine.impact_of(
            trip.id, amount="1740", travelers=3, replaces_source_type="flight_offer"
        )
        # 4000 - 1740, not 4000 - 1875 - 1740.
        assert impact.remaining_after == Decimal("2260.00")

    def test_an_over_budget_offer_is_flagged_not_hidden(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.set_budget(trip.id, total_budget="4000", emergency_reserve=0)
        impact = engine.impact_of(trip.id, amount="4500", travelers=3)
        assert impact.within_budget is False
        assert impact.verdict_after == "over_budget"
        assert impact.remaining_after == Decimal("-500.00")

    def test_a_mock_price_is_never_marked_payable(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        impact = engine.impact_of(trip.id, amount="1875", source=SOURCE_MOCK)
        assert impact.payable is False
        assert impact.source == SOURCE_MOCK

    def test_a_preview_writes_nothing(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session)
        engine.impact_of(trip.id, amount="1875", travelers=3)
        _, total = engine.ledger(trip.id)
        assert total == 0
        assert engine.snapshot(trip.id).allocated_cost == Decimal("0.00")

    def test_impact_without_a_budget_answers_honestly(
        self, db_session: Session, engine: BudgetEngine
    ) -> None:
        trip = make_trip(db_session, budget=None)
        impact = engine.impact_of(trip.id, amount="1875", travelers=3)
        assert impact.remaining_after is None
        assert impact.within_budget is None
        assert impact.percentage_of_budget is None
