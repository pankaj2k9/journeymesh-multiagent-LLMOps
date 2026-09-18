"""Assembling the traveller dashboard.

Every number here is read from the service that owns it - the budget engine for
money, the selections for arrangement progress - rather than recomputed. A
dashboard that does its own arithmetic is a dashboard that eventually disagrees
with the page it links to.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SelectedOffer, Trip, TripBudget
from app.db.repositories import OfferRepository
from app.schemas.common import ensure_utc
from app.schemas.dashboard import (
    BookingProgress,
    BudgetProgress,
    DashboardCounts,
    DashboardResponse,
    NextItem,
    TripCard,
)
from app.services.auth_service import user_out
from app.services.budget_engine import BudgetEngine, verdict_for
from app.services.money import Money, to_decimal

# What a fully arranged journey has. Activities are optional - a trip with no
# excursions is not an unfinished trip - so they add to the count only once at
# least one has been chosen.
_CORE_PARTS = 2


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.offers = OfferRepository(session)
        self.budgets = BudgetEngine(session)

    def build(
        self,
        *,
        user: Any = None,
        session_id: str | None = None,
        today: date | None = None,
        limit: int = 50,
    ) -> DashboardResponse:
        reference = today or datetime.now(timezone.utc).date()
        trips = self._trips_for(user=user, session_id=session_id, limit=limit)

        cards = [self._card(trip, reference) for trip in trips]
        upcoming = [card for card in cards if card.bucket == "upcoming"]
        drafts = [card for card in cards if card.bucket == "draft"]
        past = [card for card in cards if card.bucket == "past"]

        # Soonest first for what is ahead; most recent first for what is behind.
        upcoming.sort(key=lambda card: (card.departure_date or date.max))
        past.sort(key=lambda card: (card.departure_date or date.min), reverse=True)

        return DashboardResponse(
            user=user_out(user) if user is not None else None,
            anonymous=user is None,
            counts=DashboardCounts(
                upcoming=len(upcoming),
                drafts=len(drafts),
                past=len(past),
                total=len(cards),
            ),
            upcoming=upcoming,
            drafts=drafts,
            past=past,
            generated_at=datetime.now(timezone.utc),
        )

    # ---- scope -----------------------------------------------------------
    def _trips_for(
        self, *, user: Any, session_id: str | None, limit: int
    ) -> list[Trip]:
        """A signed-in traveller's journeys, or this browser session's.

        Never both. Falling back to the session for a signed-in user would show
        one person another's journeys whenever a shared machine reused a
        session id.
        """
        stmt = select(Trip)
        if user is not None:
            stmt = stmt.where(Trip.user_id == user.id)
        elif session_id:
            stmt = stmt.where(Trip.session_id == session_id, Trip.user_id.is_(None))
        else:
            return []
        stmt = stmt.order_by(Trip.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    # ---- one card --------------------------------------------------------
    def _card(self, trip: Trip, today: date) -> TripCard:
        bucket, days_until = _bucket_for(trip, today)
        nights = None
        if trip.departure_date and trip.return_date:
            nights = max((trip.return_date - trip.departure_date).days, 0)

        return TripCard(
            trip_id=trip.id,
            bucket=bucket,
            origin=trip.origin,
            destination=trip.destination,
            departure_date=trip.departure_date,
            return_date=trip.return_date,
            nights=nights,
            travelers=trip.travelers or 1,
            status=trip.status,
            review_status=trip.review_status,
            preferred_language=trip.preferred_language or "en",
            days_until_departure=days_until,
            budget=self._budget(trip),
            booking=self._booking(trip),
            next_item=self._next_item(trip),
            created_at=trip.created_at,
            updated_at=trip.updated_at,
        )

    def _budget(self, trip: Trip) -> BudgetProgress:
        """Read the cached budget row; never open one from a list view.

        ``BudgetEngine.ensure`` would create a budget for every trip the
        dashboard touches, turning a read into dozens of writes. A trip that
        has never had a budget simply reports the planning ceiling from its own
        row, which is what the traveller entered.
        """
        record = self.session.scalar(
            select(TripBudget).where(TripBudget.trip_id == trip.id)
        )
        if record is None:
            currency = trip.currency or "USD"
            # Rounded to the currency's own precision, like every other endpoint
            # that returns money. Storage keeps four places so a per-traveller
            # split multiplies back exactly; that is not what a card shows.
            total = (
                Money(to_decimal(trip.budget), currency).rounded_amount()
                if trip.budget is not None
                else None
            )
            return BudgetProgress(
                currency=currency,
                total_budget=total,
                committed_cost=Money.zero(currency).rounded_amount(),
                planned_cost=Money.zero(currency).rounded_amount(),
                allocated_cost=Money.zero(currency).rounded_amount(),
                remaining_budget=total,
                verdict="no_budget_set" if total is None else "within_budget",
                percentage_used=0.0 if total is not None else None,
            )

        allocated = (
            to_decimal(record.committed_cost)
            + to_decimal(record.planned_cost)
            + to_decimal(record.estimated_cost)
        )
        total = to_decimal(record.total_budget) if record.total_budget is not None else None
        reserve = to_decimal(record.emergency_reserve)
        remaining = total - reserve - allocated if total is not None else None

        percentage = None
        if total is not None and total > 0:
            percentage = float(round(allocated / total * 100, 1))

        currency = record.currency
        verdict = verdict_for(
            Money(remaining, currency) if remaining is not None else None,
            Money(total, currency) if total is not None else None,
            Money(allocated, currency),
        )

        def shown(value: Any) -> Any:
            return None if value is None else Money(value, currency).rounded_amount()

        return BudgetProgress(
            currency=currency,
            total_budget=shown(total),
            committed_cost=shown(to_decimal(record.committed_cost)),
            planned_cost=shown(to_decimal(record.planned_cost)),
            allocated_cost=shown(allocated),
            remaining_budget=shown(remaining),
            percentage_used=percentage,
            verdict=verdict,
        )

    def _booking(self, trip: Trip) -> BookingProgress:
        selections = self.offers.active_selections(trip.id)
        kinds = [selection.kind for selection in selections]

        flight = "flight" in kinds
        hotel = "hotel" in kinds
        activities = sum(1 for kind in kinds if kind == "activity")

        # Flights and accommodation are what a journey needs; activities count
        # once, as a single "something planned to do".
        parts_done = int(flight) + int(hotel) + (1 if activities else 0)
        parts_total = _CORE_PARTS + (1 if activities else 0)
        percent = int(round(parts_done / parts_total * 100)) if parts_total else 0

        return BookingProgress(
            flight_selected=flight,
            hotel_selected=hotel,
            activity_count=activities,
            selected_count=len(selections),
            # A selection is not a booking. This stays zero until the booking
            # flow exists, and the two are never summed.
            booked_count=0,
            percent=percent,
        )

    def _next_item(self, trip: Trip) -> NextItem | None:
        """The next thing that happens, from what has actually been chosen."""
        selections = self.offers.active_selections(trip.id)
        if not selections:
            return None

        candidates: list[tuple[datetime | None, SelectedOffer]] = []
        for selection in selections:
            candidates.append((_starts_at(selection), selection))

        dated = [pair for pair in candidates if pair[0] is not None]
        chosen = min(dated, key=lambda pair: pair[0])[1] if dated else candidates[0][1]
        offer = chosen.offer

        return NextItem(
            kind=chosen.kind,
            title=offer.title if offer else chosen.kind,
            starts_at=_starts_at(chosen),
            starts_on=trip.departure_date,
            source=offer.source if offer else "MOCK",
        )


# ---- helpers ------------------------------------------------------------
def _bucket_for(trip: Trip, today: date) -> tuple[str, int | None]:
    """Which shelf a journey belongs on, and how long until it starts.

    The order of the checks is the definition:

      * a journey whose last date has passed is **past**, whatever its review
        state - an unapproved trip to last March is not a draft to work on;
      * anything still awaiting a human is a **draft**;
      * everything else, including a trip with no dates yet, is **upcoming**
        only if it actually has a departure date. A dateless approved plan has
        nothing to count down to, so it stays a draft.
    """
    end = trip.return_date or trip.departure_date
    if end is not None and end < today:
        days = (trip.departure_date - today).days if trip.departure_date else None
        return "past", days

    if trip.review_status != "approved":
        days = (trip.departure_date - today).days if trip.departure_date else None
        return "draft", days

    if trip.departure_date is None:
        return "draft", None

    return "upcoming", (trip.departure_date - today).days


def _starts_at(selection: SelectedOffer) -> datetime | None:
    """When a chosen offer begins, read out of its stored snapshot."""
    offer = selection.offer
    if offer is None:
        return None
    payload = offer.payload or {}

    if selection.kind == "flight":
        slices = payload.get("slices") or []
        if slices:
            segments = slices[0].get("segments") or []
            if segments:
                return _parse(segments[0].get("departure_time"))
        return None

    if selection.kind == "hotel":
        check_in = payload.get("check_in")
        if check_in:
            parsed = _parse(check_in)
            if parsed:
                return parsed
    return None


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    try:
        text = str(value)
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


__all__ = ["DashboardService"]
