"""The budget engine.

This is the only thing in Travel Crew AI allowed to decide what a journey
costs. No agent, no prompt and no provider payload writes a total; they supply
amounts, and the engine decides what those amounts mean.

The design is a ledger plus a cache:

  * ``budget_items`` is append-only. A selection adds a line, a change adds a
    reversal and a new line, and a deletion is a reversal. Nothing is edited,
    so "Flight selected +$1,840 / Hotel booked +$720 / Museum removed -$80" is
    the table itself rather than a story assembled afterwards.
  * ``trip_budgets`` caches the sums so a dashboard does not re-add the ledger
    on every render. ``recompute`` is its only writer and it is optimistically
    locked, so two selections racing each other cannot both read 4000 and both
    write 2164.

Every amount is ``Decimal`` and every combination goes through ``Money``, which
refuses to add two currencies. A trip has exactly one currency; there is no
exchange rate in this system, and inventing one would put a fabricated number
on a page that a traveller reads as a price.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import (
    BUDGET_CATEGORIES,
    BUDGET_ITEM_STATES,
    BUDGET_ITEM_TRANSITIONS,
    CATEGORY_ACCOMMODATION,
    CATEGORY_ACTIVITY,
    CATEGORY_FLIGHT,
    CATEGORY_FOOD,
    CATEGORY_LOCAL_TRANSPORT,
    CATEGORY_MISCELLANEOUS,
    COMMITTED_STATES,
    DEFAULT_RESERVE_RATIO,
    ESTIMATED_STATES,
    EVENT_BUDGET_ITEM_ADDED,
    EVENT_BUDGET_ITEM_PROMOTED,
    EVENT_BUDGET_ITEM_REVERSED,
    ITEM_ESTIMATED,
    ITEM_SELECTED,
    NEAR_LIMIT_THRESHOLD,
    PAYABLE_SOURCES,
    PLANNED_STATES,
    SOURCE_ESTIMATE,
)
from app.core.exceptions import (
    BudgetConflict,
    BudgetItemNotFound,
    CurrencyConflict,
    InvalidBudgetTransition,
    TripNotFound,
)
from app.db.models import BudgetItem, Trip, TripBudget
from app.db.repositories import BudgetRepository
from app.observability.logging import get_logger
from app.schemas.budget_ledger import (
    BudgetImpact,
    BudgetItemOut,
    CategoryTotals,
    TripBudgetOut,
)
from app.security import audit
from app.services.currency import ConvertedAmount, ExchangeRate, apply
from app.services.money import Money, normalise_currency, percentage_of, to_decimal

logger = get_logger("journeymesh.services.budget")

# How many times a recompute retries when another writer wins the version race.
# Three is plenty for a per-trip lock; beyond that something is genuinely
# contended and the caller should be told rather than spun on.
_MAX_RECOMPUTE_ATTEMPTS = 3

# Which cached column each category rolls up into.
_CATEGORY_COLUMN = {
    CATEGORY_FLIGHT: "flight_cost",
    CATEGORY_ACCOMMODATION: "accommodation_cost",
    CATEGORY_ACTIVITY: "activity_cost",
    CATEGORY_LOCAL_TRANSPORT: "local_transport_cost",
    CATEGORY_FOOD: "food_estimate",
    CATEGORY_MISCELLANEOUS: "miscellaneous_estimate",
}


@dataclass(frozen=True)
class LedgerTotals:
    """The sums a ledger produces. Pure data, no database."""

    currency: str
    committed: Money
    planned: Money
    estimated: Money
    by_category: dict[str, Money]

    @property
    def allocated(self) -> Money:
        return self.committed + self.planned + self.estimated


def summarise(items: list[BudgetItem], currency: str) -> LedgerTotals:
    """Add up a ledger.

    A standalone function rather than a method because it is the part worth
    testing without a database, and because the ranking and preview paths need
    it over lines that have not been written yet.

    Reversals are ordinary rows with a negative amount, so they need no special
    case here - they simply subtract.
    """
    currency = normalise_currency(currency)
    committed = Money.zero(currency)
    planned = Money.zero(currency)
    estimated = Money.zero(currency)
    by_category = {category: Money.zero(currency) for category in BUDGET_CATEGORIES}

    for item in items:
        if normalise_currency(item.currency) != currency:
            raise CurrencyConflict(
                f"budget line {item.id} is in {item.currency}, "
                f"but the journey is budgeted in {currency}"
            )
        amount = Money(to_decimal(item.amount), currency)

        if item.state in COMMITTED_STATES:
            committed = committed + amount
        elif item.state in PLANNED_STATES:
            planned = planned + amount
        elif item.state in ESTIMATED_STATES:
            estimated = estimated + amount

        if item.category in by_category:
            by_category[item.category] = by_category[item.category] + amount

    return LedgerTotals(
        currency=currency,
        committed=committed,
        planned=planned,
        estimated=estimated,
        by_category=by_category,
    )


def verdict_for(remaining: Money | None, total_budget: Money | None, allocated: Money) -> str:
    """Name the budget situation.

    ``near_limit`` fires at 92% of the budget, the same threshold the budget
    agent has always used, so the draft plan and the live budget cannot
    disagree about whether a journey is close to its ceiling.
    """
    if total_budget is None or total_budget.amount <= 0:
        return "no_budget_set"
    if remaining is not None and remaining.is_negative:
        return "over_budget"
    ratio = allocated.amount / total_budget.amount
    if ratio > Decimal(1):
        return "over_budget"
    if ratio >= to_decimal(NEAR_LIMIT_THRESHOLD):
        return "near_limit"
    return "within_budget"


class BudgetEngine:
    """Deterministic budget arithmetic for one database session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.budgets = BudgetRepository(session)

    # ---- lifecycle -------------------------------------------------------
    def ensure(
        self,
        trip_id: str,
        *,
        currency: str | None = None,
        total_budget: Any = None,
        emergency_reserve: Any = None,
    ) -> TripBudget:
        """Get this trip's budget record, creating it on first use.

        Called from trip creation and from every read path, so a trip planned
        before this feature existed grows a budget the first time one is asked
        for rather than 404-ing.
        """
        trip = self.session.get(Trip, trip_id)
        if trip is None:
            raise TripNotFound(f"trip {trip_id} does not exist")

        record = self.budgets.get_budget(trip_id)
        resolved_currency = normalise_currency(currency or trip.currency or "USD")

        if record is None:
            total = to_decimal(total_budget) if total_budget is not None else None
            if total is None and trip.budget is not None:
                # Carry the planning budget across from the legacy float column.
                total = to_decimal(trip.budget)
            reserve = (
                to_decimal(emergency_reserve)
                if emergency_reserve is not None
                else _default_reserve(total)
            )
            record = self.budgets.create_budget(
                trip_id,
                currency=resolved_currency,
                total_budget=total,
                emergency_reserve=reserve,
            )
            return record

        updates: dict[str, Any] = {}
        if total_budget is not None:
            updates["total_budget"] = to_decimal(total_budget)
        if emergency_reserve is not None:
            updates["emergency_reserve"] = to_decimal(emergency_reserve)
        if currency is not None and resolved_currency != record.currency:
            # Changing currency after money is on the ledger would silently
            # revalue every line, so it is refused rather than converted.
            if self.budgets.count_items(trip_id) > 0:
                raise CurrencyConflict(
                    "this journey already has costs recorded in "
                    f"{record.currency} and cannot be re-denominated"
                )
            updates["currency"] = resolved_currency
        if updates:
            for key, value in updates.items():
                setattr(record, key, value)
            self.session.flush()
        return record

    # ---- reads -----------------------------------------------------------
    def snapshot(self, trip_id: str) -> TripBudgetOut:
        """The current budget picture, recomputed from the ledger."""
        return self.recompute(trip_id)

    def ledger(
        self, trip_id: str, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[BudgetItemOut], int]:
        items = self.budgets.items(trip_id, limit=limit, offset=offset)
        total = self.budgets.count_items(trip_id)
        return [_to_out(item) for item in items], total

    # ---- the one writer of totals ---------------------------------------
    def recompute(self, trip_id: str) -> TripBudgetOut:
        """Re-derive every cached total from the ledger and store it.

        Retries on a lost version race. The retry is safe because the whole
        computation is a pure function of rows that are never edited: re-running
        it after someone else's insert simply includes that insert.
        """
        record = self.ensure(trip_id)
        for attempt in range(_MAX_RECOMPUTE_ATTEMPTS):
            expected_version = record.version
            items = self.budgets.active_items(trip_id)
            totals = summarise(items, record.currency)

            columns: dict[str, Any] = {
                "committed_cost": totals.committed.amount,
                "planned_cost": totals.planned.amount,
                "estimated_cost": totals.estimated.amount,
            }
            for category, column in _CATEGORY_COLUMN.items():
                columns[column] = totals.by_category[category].amount

            if self.budgets.apply_totals(record, expected_version, **columns):
                return _to_budget_out(record, totals)

            logger.info(
                "budget recompute lost the version race, retrying",
                extra={"trip_id": trip_id, "attempt": attempt + 1},
            )
            self.session.refresh(record)

        raise BudgetConflict(
            f"budget for trip {trip_id} is being changed by another request"
        )

    # ---- ledger writes ---------------------------------------------------
    def add_item(
        self,
        trip_id: str,
        *,
        category: str,
        amount: Any,
        state: str = ITEM_ESTIMATED,
        label: str = "",
        currency: str | None = None,
        source: str = SOURCE_ESTIMATE,
        source_type: str | None = None,
        source_id: str | None = None,
        created_by: str = "budget_engine",
        detail: dict[str, Any] | None = None,
        replaces_source_type: str | None = None,
        user_asserted: bool = False,
        rate: ExchangeRate | None = None,
    ) -> tuple[BudgetItemOut, TripBudgetOut]:
        """Append one line and return it with the budget it produced.

        ``replaces_source_type`` is what makes "choose a different flight"
        correct: the previous lines of that kind are reversed in the same
        transaction, so the ledger shows the swap and the totals never
        double-count two flights.

        ``user_asserted`` marks a line the traveller entered themselves - the
        taxi they already paid for. It is the one way a committed line can
        exist without a provider behind it, because there the person *is* the
        source. It never applies to a price: an agent or an offer claiming to
        be payable still has to prove it with a payable source.

        ``rate`` is required when the amount is not already in the journey's
        base currency. A taka-budgeted trip absorbs a dollar flight and a euro
        hotel, but only through a rate that is *passed in and then stored on
        the row*. The engine never fetches one itself: that would make an
        ambient exchange rate exist inside the one component that must stay
        deterministic, and a total that changes depending on when it was
        recomputed is not a total.
        """
        record = self.ensure(trip_id)
        _validate_category(category)
        _validate_state(state)

        resolved_currency = normalise_currency(currency or record.currency)
        conversion: ConvertedAmount | None = None

        if resolved_currency != record.currency:
            if rate is None:
                raise CurrencyConflict(
                    f"this journey is budgeted in {record.currency}; an amount in "
                    f"{resolved_currency} needs an exchange rate to be recorded with it"
                )
            if rate.source_currency != resolved_currency or rate.target_currency != record.currency:
                raise CurrencyConflict(
                    f"the supplied rate is {rate.source_currency}->{rate.target_currency}, "
                    f"but this line converts {resolved_currency}->{record.currency}"
                )
            conversion = apply(Money(to_decimal(amount), resolved_currency), rate)

        if state in COMMITTED_STATES and source not in PAYABLE_SOURCES and not user_asserted:
            # A BOOKED or PAID line asserts a real obligation. Only a provider
            # confirmation creates one - an estimate, a mock or a model's
            # suggestion never can - unless the traveller is reporting money
            # they spent themselves.
            raise InvalidBudgetTransition(
                f"a {state} budget line needs a payable source, not {source}"
            )

        if replaces_source_type:
            self._reverse_source_type(trip_id, replaces_source_type, record.currency)

        # `amount`/`currency` on the row are always the journey's base currency,
        # because that is what gets summed. The provider's own figure survives
        # untouched beside it.
        money = (
            conversion.converted
            if conversion is not None
            else Money(to_decimal(amount), resolved_currency)
        )
        item = self.budgets.add_item(
            trip_id=trip_id,
            category=category,
            state=state,
            label=label[:200],
            amount=money.amount,
            currency=record.currency,
            original_amount=conversion.original.amount if conversion else None,
            original_currency=conversion.original.currency if conversion else None,
            exchange_rate=conversion.rate.rate if conversion else None,
            exchange_rate_source=conversion.rate.source if conversion else None,
            exchange_rate_at=conversion.rate.retrieved_at if conversion else None,
            source=source,
            source_type=source_type,
            source_id=source_id,
            created_by=created_by,
            detail={**(detail or {}), **({"user_asserted": True} if user_asserted else {})},
        )
        audit.record(
            EVENT_BUDGET_ITEM_ADDED,
            trip_id=trip_id,
            detail={
                "category": category,
                "state": state,
                "amount": money.as_str(),
                "currency": record.currency,
                "source": source,
                "created_by": created_by,
                **(
                    {
                        "original_amount": conversion.original.as_str(),
                        "original_currency": conversion.original.currency,
                        "exchange_rate": format(conversion.rate.rate, "f"),
                        "exchange_rate_source": conversion.rate.source,
                    }
                    if conversion
                    else {}
                ),
            },
            session=self.session,
        )
        return _to_out(item), self.recompute(trip_id)

    def reverse_item(
        self, trip_id: str, item_id: str, *, actor: str = "user", reason: str | None = None
    ) -> tuple[BudgetItemOut, TripBudgetOut]:
        """Cancel a line by appending its negation. The original is untouched."""
        original = self.budgets.get_item(item_id, trip_id=trip_id)
        if original is None:
            raise BudgetItemNotFound(f"budget line {item_id} does not exist on this journey")
        if original.reverses_id is not None:
            raise InvalidBudgetTransition("a reversal cannot itself be reversed")
        if original.id in self.budgets.reversed_ids(trip_id):
            raise InvalidBudgetTransition("that budget line has already been reversed")

        reversal = self._append_reversal(original, actor=actor, reason=reason)
        return _to_out(reversal), self.recompute(trip_id)

    def promote(
        self, trip_id: str, item_id: str, *, to_state: str, source: str | None = None
    ) -> tuple[BudgetItemOut, TripBudgetOut]:
        """Move a line along the commitment ladder.

        ESTIMATED -> SELECTED -> BOOKED -> PAID, and never backwards. Going
        back is a reversal plus a new line, which is the same thing the ledger
        would have to record anyway.
        """
        item = self.budgets.get_item(item_id, trip_id=trip_id)
        if item is None:
            raise BudgetItemNotFound(f"budget line {item_id} does not exist on this journey")
        _validate_state(to_state)

        allowed = BUDGET_ITEM_TRANSITIONS.get(item.state, ())
        if to_state not in allowed:
            raise InvalidBudgetTransition(
                f"a {item.state} budget line cannot become {to_state}"
            )

        effective_source = source or item.source
        if to_state in COMMITTED_STATES and effective_source not in PAYABLE_SOURCES:
            raise InvalidBudgetTransition(
                f"a {to_state} budget line needs a payable source, not {effective_source}"
            )

        previous = item.state
        item.state = to_state
        if source:
            item.source = source
        self.session.flush()
        audit.record(
            EVENT_BUDGET_ITEM_PROMOTED,
            trip_id=trip_id,
            detail={"item_id": item_id, "from": previous, "to": to_state},
            session=self.session,
        )
        return _to_out(item), self.recompute(trip_id)

    def set_budget(
        self,
        trip_id: str,
        *,
        total_budget: Any = None,
        emergency_reserve: Any = None,
    ) -> TripBudgetOut:
        self.ensure(
            trip_id, total_budget=total_budget, emergency_reserve=emergency_reserve
        )
        return self.recompute(trip_id)

    # ---- the question every offer card asks ------------------------------
    def impact_of(
        self,
        trip_id: str,
        *,
        amount: Any,
        currency: str | None = None,
        travelers: int = 1,
        label: str = "",
        source: str = SOURCE_ESTIMATE,
        replaces_source_type: str | None = None,
        state: str = ITEM_SELECTED,
        rate: ExchangeRate | None = None,
    ) -> BudgetImpact:
        """What would happen to this budget if the traveller chose this.

        Writes nothing. The same function backs the preview endpoint and the
        selection endpoint, so the "$2,164 remaining after selection" on a
        result card is produced by the code that will actually do the selecting
        rather than by a second implementation that can drift from it.
        """
        record = self.ensure(trip_id)
        currency_code = normalise_currency(currency or record.currency)

        converted_preview: ConvertedAmount | None = None
        if currency_code != record.currency:
            if rate is None:
                raise CurrencyConflict(
                    f"this journey is budgeted in {record.currency}; previewing an "
                    f"amount in {currency_code} needs an exchange rate"
                )
            converted_preview = apply(Money(to_decimal(amount), currency_code), rate)
            amount = converted_preview.converted.amount

        items = self.budgets.active_items(trip_id)
        before = summarise(items, record.currency)

        # Choosing a new flight replaces the old one rather than adding to it.
        displaced = Money.zero(record.currency)
        if replaces_source_type:
            for item in items:
                if item.source_type == replaces_source_type and item.state == state:
                    displaced = displaced + Money(to_decimal(item.amount), record.currency)

        item_total = Money(to_decimal(amount), record.currency)
        total_budget = (
            Money(to_decimal(record.total_budget), record.currency)
            if record.total_budget is not None
            else None
        )
        reserve = Money(to_decimal(record.emergency_reserve), record.currency)

        allocated_before = before.allocated
        allocated_after = allocated_before - displaced + item_total

        remaining_before = (
            total_budget - reserve - allocated_before if total_budget is not None else None
        )
        remaining_after = (
            total_budget - reserve - allocated_after if total_budget is not None else None
        )

        head_count = max(int(travelers or 1), 1)
        return BudgetImpact(
            trip_id=trip_id,
            currency=record.currency,
            label=label,
            item_total=item_total.rounded_amount(),
            per_traveler=item_total.divided_by(head_count).rounded_amount(),
            travelers=head_count,
            total_budget=total_budget.rounded_amount() if total_budget is not None else None,
            committed_before=before.committed.rounded_amount(),
            allocated_before=allocated_before.rounded_amount(),
            remaining_before=(
                remaining_before.rounded_amount() if remaining_before is not None else None
            ),
            remaining_after=(
                remaining_after.rounded_amount() if remaining_after is not None else None
            ),
            percentage_of_budget=_percentage(item_total, total_budget),
            within_budget=(
                None if remaining_after is None else not remaining_after.is_negative
            ),
            verdict_after=verdict_for(remaining_after, total_budget, allocated_after),
            payable=source in PAYABLE_SOURCES,
            source=source,
            original_amount=(
                converted_preview.original.rounded_amount() if converted_preview else None
            ),
            original_currency=(
                converted_preview.original.currency if converted_preview else None
            ),
            exchange_rate=converted_preview.rate.rate if converted_preview else None,
            exchange_rate_source=(
                converted_preview.rate.source if converted_preview else None
            ),
        )

    # ---- internals -------------------------------------------------------
    def _reverse_source_type(self, trip_id: str, source_type: str, currency: str) -> None:
        for item in self.budgets.active_items(trip_id, source_type=source_type):
            self._append_reversal(item, actor="budget_engine", reason="replaced")

    def _append_reversal(
        self, original: BudgetItem, *, actor: str, reason: str | None
    ) -> BudgetItem:
        reversal = self.budgets.add_item(
            trip_id=original.trip_id,
            category=original.category,
            state=original.state,
            label=f"Reversal: {original.label}"[:200],
            amount=-to_decimal(original.amount),
            currency=original.currency,
            source=original.source,
            source_type=original.source_type,
            source_id=original.source_id,
            created_by=actor,
            reverses_id=original.id,
            # The reversal mirrors the original's provider figure as well as
            # its converted one, so the audit trail balances in both currencies.
            original_amount=(
                -to_decimal(original.original_amount)
                if original.original_amount is not None
                else None
            ),
            original_currency=original.original_currency,
            exchange_rate=original.exchange_rate,
            exchange_rate_source=original.exchange_rate_source,
            exchange_rate_at=original.exchange_rate_at,
            detail={"reason": reason} if reason else {},
        )
        audit.record(
            EVENT_BUDGET_ITEM_REVERSED,
            trip_id=original.trip_id,
            detail={"item_id": original.id, "reason": reason, "actor": actor},
            session=self.session,
        )
        return reversal


# ---- module helpers -----------------------------------------------------
def _default_reserve(total: Decimal | None) -> Decimal:
    if total is None or total <= 0:
        return Decimal(0)
    return (total * to_decimal(DEFAULT_RESERVE_RATIO)).quantize(Decimal("0.0001"))


def _percentage(part: Money, whole: Money | None) -> float | None:
    if whole is None:
        return None
    share = percentage_of(part, whole)
    return float(share) if share is not None else None


def _validate_category(category: str) -> None:
    if category not in BUDGET_CATEGORIES:
        raise InvalidBudgetTransition(f"unknown budget category: {category}")


def _validate_state(state: str) -> None:
    if state not in BUDGET_ITEM_STATES:
        raise InvalidBudgetTransition(f"unknown budget state: {state}")


def _to_out(item: BudgetItem) -> BudgetItemOut:
    # Displayed at the currency's own precision. The column keeps four places
    # so that a per-traveller split multiplies back exactly; a ledger row that
    # rendered "80.0000" would just be leaking that storage detail into the UI.
    return BudgetItemOut(
        id=item.id,
        trip_id=item.trip_id,
        category=item.category,
        state=item.state,
        label=item.label,
        amount=Money(to_decimal(item.amount), item.currency).rounded_amount(),
        currency=item.currency,
        source=item.source,
        source_type=item.source_type,
        source_id=item.source_id,
        created_by=item.created_by,
        reverses_id=item.reverses_id,
        created_at=item.created_at,
        original_amount=(
            Money(to_decimal(item.original_amount), item.original_currency).rounded_amount()
            if item.original_amount is not None and item.original_currency
            else None
        ),
        original_currency=item.original_currency,
        exchange_rate=item.exchange_rate,
        exchange_rate_source=item.exchange_rate_source,
        exchange_rate_at=item.exchange_rate_at,
    )


def _to_budget_out(record: TripBudget, totals: LedgerTotals) -> TripBudgetOut:
    currency = record.currency
    total_budget = (
        Money(to_decimal(record.total_budget), currency)
        if record.total_budget is not None
        else None
    )
    reserve = Money(to_decimal(record.emergency_reserve), currency)
    allocated = totals.allocated
    remaining = total_budget - reserve - allocated if total_budget is not None else None
    used = percentage_of(allocated, total_budget) if total_budget is not None else None

    return TripBudgetOut(
        trip_id=record.trip_id,
        currency=currency,
        total_budget=total_budget.rounded_amount() if total_budget is not None else None,
        emergency_reserve=reserve.rounded_amount(),
        committed_cost=totals.committed.rounded_amount(),
        planned_cost=totals.planned.rounded_amount(),
        estimated_cost=totals.estimated.rounded_amount(),
        allocated_cost=allocated.rounded_amount(),
        remaining_budget=remaining.rounded_amount() if remaining is not None else None,
        categories=CategoryTotals(
            flight_cost=totals.by_category[CATEGORY_FLIGHT].rounded_amount(),
            accommodation_cost=totals.by_category[CATEGORY_ACCOMMODATION].rounded_amount(),
            activity_cost=totals.by_category[CATEGORY_ACTIVITY].rounded_amount(),
            local_transport_cost=totals.by_category[CATEGORY_LOCAL_TRANSPORT].rounded_amount(),
            food_estimate=totals.by_category[CATEGORY_FOOD].rounded_amount(),
            miscellaneous_estimate=totals.by_category[CATEGORY_MISCELLANEOUS].rounded_amount(),
        ),
        verdict=verdict_for(remaining, total_budget, allocated),
        percentage_used=float(used) if used is not None else None,
        version=record.version,
        recomputed_at=record.recomputed_at or datetime.now(timezone.utc),
    )


__all__ = ["BudgetEngine", "LedgerTotals", "summarise", "verdict_for"]
