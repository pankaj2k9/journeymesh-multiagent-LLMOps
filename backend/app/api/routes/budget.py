"""Budget endpoints.

Every number returned here comes from ``BudgetEngine``. No route computes a
total, and no model is consulted: the arithmetic behind "remaining after this
selection" is the same code whether it was reached from a result card, the
budget page or the assistant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import budget_engine, optional_user
from app.core.constants import ITEM_SELECTED, SOURCE_ESTIMATE
from app.db.models import User
from app.schemas.budget_ledger import (
    BudgetImpact,
    BudgetItemOut,
    ExpenseCreate,
    LedgerResponse,
    TripBudgetOut,
)
from app.schemas.common import TravelCrewModel
from app.schemas.money import MoneyAmount
from app.services.budget_engine import BudgetEngine

router = APIRouter(prefix="/trips", tags=["budget"])


class BudgetSettings(TravelCrewModel):
    """Change the ceiling or the reserve, not the spend."""

    total_budget: MoneyAmount | None = None
    emergency_reserve: MoneyAmount | None = None


class ImpactRequest(TravelCrewModel):
    """Ask what one choice would cost, without making it.

    ``replaces_source_type`` is how "swap this flight for that one" is asked:
    the existing selection of that kind is netted out rather than added to, so
    the preview matches what selecting would actually do.
    """

    amount: MoneyAmount
    travelers: int = 1
    label: str = ""
    currency: str | None = None
    source: str = SOURCE_ESTIMATE
    replaces_source_type: str | None = None


@router.get(
    "/{trip_id}/budget",
    response_model=TripBudgetOut,
    summary="The budget for one journey",
    description=(
        "Recomputed from the ledger on every read, so the totals can never drift "
        "from the lines that produced them."
    ),
)
def read_budget(
    trip_id: str,
    engine: BudgetEngine = Depends(budget_engine),
) -> TripBudgetOut:
    return engine.snapshot(trip_id)


@router.put(
    "/{trip_id}/budget",
    response_model=TripBudgetOut,
    summary="Set the total budget or the emergency reserve",
)
def update_budget(
    trip_id: str,
    payload: BudgetSettings,
    engine: BudgetEngine = Depends(budget_engine),
) -> TripBudgetOut:
    return engine.set_budget(
        trip_id,
        total_budget=payload.total_budget,
        emergency_reserve=payload.emergency_reserve,
    )


@router.get(
    "/{trip_id}/budget/ledger",
    response_model=LedgerResponse,
    summary="The transaction history behind the budget",
)
def read_ledger(
    trip_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    engine: BudgetEngine = Depends(budget_engine),
) -> LedgerResponse:
    items, total = engine.ledger(trip_id, limit=limit, offset=offset)
    return LedgerResponse(items=items, total=total, budget=engine.snapshot(trip_id))


@router.post(
    "/{trip_id}/budget/impact",
    response_model=BudgetImpact,
    summary="What choosing this would do to the budget",
    description=(
        "Writes nothing. This is the endpoint behind the 'remaining after selection' "
        "line on every flight, hotel and activity card."
    ),
)
def budget_impact(
    trip_id: str,
    payload: ImpactRequest,
    engine: BudgetEngine = Depends(budget_engine),
) -> BudgetImpact:
    return engine.impact_of(
        trip_id,
        amount=payload.amount,
        currency=payload.currency,
        travelers=payload.travelers,
        label=payload.label,
        source=payload.source,
        replaces_source_type=payload.replaces_source_type,
        state=ITEM_SELECTED,
    )


@router.post(
    "/{trip_id}/budget/expenses",
    response_model=LedgerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an expense by hand",
    description=(
        "Only `ESTIMATED` and `PAID` lines can be entered this way. `SELECTED` and "
        "`BOOKED` belong to the selection and booking flows, so a request body can "
        "never claim that something was booked."
    ),
)
def add_expense(
    trip_id: str,
    payload: ExpenseCreate,
    engine: BudgetEngine = Depends(budget_engine),
    user: User | None = Depends(optional_user),
) -> LedgerResponse:
    item, budget = engine.add_item(
        trip_id,
        category=payload.category,
        amount=payload.amount,
        state=payload.state,
        label=payload.label,
        currency=payload.currency,
        # A hand-entered amount is exactly as good as the person entering it,
        # and is never a provider price.
        source=SOURCE_ESTIMATE,
        source_type="manual_expense",
        created_by=user.id if user else "user",
        # A person reporting what they spent is the source of that fact, which
        # is the one way a PAID line exists without a provider behind it.
        user_asserted=True,
        detail={"note": payload.note} if payload.note else {},
    )
    return LedgerResponse(items=[item], total=1, budget=budget)


@router.delete(
    "/{trip_id}/budget/expenses/{item_id}",
    response_model=LedgerResponse,
    summary="Reverse a budget line",
    description=(
        "Nothing is deleted. A reversal is appended with the negated amount, so the "
        "history still shows what was removed and when."
    ),
)
def reverse_expense(
    trip_id: str,
    item_id: str,
    engine: BudgetEngine = Depends(budget_engine),
    user: User | None = Depends(optional_user),
) -> LedgerResponse:
    item, budget = engine.reverse_item(
        trip_id, item_id, actor=user.id if user else "user", reason="removed_by_user"
    )
    return LedgerResponse(items=[item], total=1, budget=budget)


__all__ = ["router", "BudgetItemOut"]
