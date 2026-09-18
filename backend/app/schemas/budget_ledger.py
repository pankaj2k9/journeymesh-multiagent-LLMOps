"""The budget engine's public shapes.

Separate from ``schemas/budget.py``, which is the *agent's* cost picture for a
draft journey and stays as it is. This module is the money a traveller is
actually committing: it is written only by ``BudgetEngine``, every amount is a
string on the wire (see ``schemas/money``), and every line says where its
number came from.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.core.constants import (
    BUDGET_CATEGORIES,
    BUDGET_ITEM_STATES,
    DATA_SOURCES,
)
from app.schemas.common import DataSource, TravelCrewModel
from app.schemas.money import MoneyAmount, OptionalMoney

BudgetCategory = Literal[
    "FLIGHT",
    "ACCOMMODATION",
    "ACTIVITY",
    "LOCAL_TRANSPORT",
    "FOOD",
    "MISCELLANEOUS",
]
BudgetItemState = Literal["ESTIMATED", "SELECTED", "BOOKED", "PAID"]
BudgetVerdict = Literal["within_budget", "near_limit", "over_budget", "no_budget_set"]

# Kept in step with the constants module; a mismatch would let a Literal drift
# away from what the database accepts.
assert set(BUDGET_CATEGORIES) == set(BudgetCategory.__args__)  # type: ignore[attr-defined]
assert set(BUDGET_ITEM_STATES) == set(BudgetItemState.__args__)  # type: ignore[attr-defined]
assert set(DATA_SOURCES) == set(DataSource.__args__)  # type: ignore[attr-defined]


class BudgetItemOut(TravelCrewModel):
    """One ledger line, as the interface reads it."""

    id: str
    trip_id: str
    category: BudgetCategory
    state: BudgetItemState
    label: str = ""
    amount: MoneyAmount
    currency: str = "USD"
    source: DataSource = "ESTIMATE"
    source_type: str | None = None
    source_id: str | None = None
    created_by: str = "budget_engine"
    reverses_id: str | None = None
    created_at: datetime | None = None

    # What the provider actually quoted, when it was not in the journey's
    # currency, and the rate used. Null on the common same-currency line.
    original_amount: OptionalMoney = None
    original_currency: str | None = None
    exchange_rate: Decimal | None = None
    exchange_rate_source: DataSource | None = None
    exchange_rate_at: datetime | None = None

    @property
    def is_reversal(self) -> bool:
        return self.reverses_id is not None

    @property
    def was_converted(self) -> bool:
        return self.original_currency is not None and self.original_currency != self.currency


class CategoryTotals(TravelCrewModel):
    """Spend by category. Every field is required by the budget dashboard."""

    flight_cost: MoneyAmount = Field(default=Decimal(0))
    accommodation_cost: MoneyAmount = Field(default=Decimal(0))
    activity_cost: MoneyAmount = Field(default=Decimal(0))
    local_transport_cost: MoneyAmount = Field(default=Decimal(0))
    food_estimate: MoneyAmount = Field(default=Decimal(0))
    miscellaneous_estimate: MoneyAmount = Field(default=Decimal(0))


class TripBudgetOut(TravelCrewModel):
    """The whole budget picture for one trip.

    ``remaining_budget`` is the number shown next to every offer, and it is
    computed one way only:

        remaining = total_budget - emergency_reserve
                    - committed_cost - planned_cost - estimated_cost

    Nothing else in the system is allowed to compute it differently, which is
    why it is returned here rather than assembled in the interface.
    """

    trip_id: str
    currency: str = "USD"

    total_budget: OptionalMoney = None
    emergency_reserve: MoneyAmount = Field(default=Decimal(0))

    committed_cost: MoneyAmount = Field(default=Decimal(0))
    planned_cost: MoneyAmount = Field(default=Decimal(0))
    estimated_cost: MoneyAmount = Field(default=Decimal(0))
    allocated_cost: MoneyAmount = Field(default=Decimal(0))
    remaining_budget: OptionalMoney = None

    categories: CategoryTotals = Field(default_factory=CategoryTotals)
    verdict: BudgetVerdict = "no_budget_set"
    percentage_used: float | None = None
    version: int = 1
    recomputed_at: datetime | None = None


class BudgetImpact(TravelCrewModel):
    """What choosing one offer would do to a trip's budget.

    Returned by the preview endpoint *and* by the selection endpoint, so the
    number the traveller was shown before confirming is the same number the
    engine wrote afterwards.
    """

    trip_id: str
    currency: str = "USD"
    label: str = ""

    item_total: MoneyAmount = Field(default=Decimal(0))
    per_traveler: OptionalMoney = None
    travelers: int = 1

    total_budget: OptionalMoney = None
    committed_before: MoneyAmount = Field(default=Decimal(0))
    allocated_before: MoneyAmount = Field(default=Decimal(0))
    remaining_before: OptionalMoney = None
    remaining_after: OptionalMoney = None

    percentage_of_budget: float | None = None
    within_budget: bool | None = None
    verdict_after: BudgetVerdict = "no_budget_set"
    # True when the amount came from a source a traveller could actually be
    # charged (LIVE or CACHED). An ESTIMATE or MOCK impact is a projection.
    payable: bool = False
    source: DataSource = "ESTIMATE"

    # Present when the offer was priced in another currency. `item_total` is
    # already in the journey's currency; these say what it was converted from.
    # A converted figure is an estimate of a future card charge, never the
    # charge itself - the provider bills in `original_currency`.
    original_amount: OptionalMoney = None
    original_currency: str | None = None
    exchange_rate: Decimal | None = None
    exchange_rate_source: DataSource | None = None


class ExpenseCreate(TravelCrewModel):
    """A manually entered expense.

    A user may only ever create an ``ESTIMATED`` or ``PAID`` line by hand.
    ``SELECTED`` and ``BOOKED`` belong to the selection and booking flows, so
    accepting them here would let a POST body claim something was booked.
    """

    category: BudgetCategory
    label: str = Field(min_length=1, max_length=200)
    amount: MoneyAmount
    state: Literal["ESTIMATED", "PAID"] = "ESTIMATED"
    currency: str | None = Field(default=None, max_length=3)
    note: str | None = Field(default=None, max_length=500)


class LedgerResponse(TravelCrewModel):
    items: list[BudgetItemOut] = Field(default_factory=list)
    total: int = 0
    budget: TripBudgetOut | None = None
