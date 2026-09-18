"""The traveller dashboard.

One aggregate rather than a page that fires eight requests and assembles the
answer itself. Two reasons: the interface must not decide what "booking
progress" or "on budget" means - those are the budget engine's and the booking
flow's definitions - and a dashboard that stitches together eight responses
shows eight different loading states and four inconsistent ones.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.auth import UserOut
from app.schemas.budget_ledger import BudgetVerdict
from app.schemas.common import LanguageCode, TravelCrewModel
from app.schemas.money import OptionalMoney

TripBucket = Literal["upcoming", "draft", "past"]


class BudgetProgress(TravelCrewModel):
    """The budget, reduced to what a card can show."""

    currency: str = "USD"
    total_budget: OptionalMoney = None
    committed_cost: OptionalMoney = None
    planned_cost: OptionalMoney = None
    allocated_cost: OptionalMoney = None
    remaining_budget: OptionalMoney = None
    percentage_used: float | None = None
    verdict: BudgetVerdict = "no_budget_set"


class BookingProgress(TravelCrewModel):
    """How far through arranging the trip the traveller is.

    ``percent`` counts the parts of a journey that are actually settled. It is
    computed here rather than in the interface so that the dashboard, the trip
    page and any later notification all agree on what "60% arranged" means.

    Booked counts stay at zero until the booking flow exists; a selection is
    not a booking and the two are never added together.
    """

    flight_selected: bool = False
    hotel_selected: bool = False
    activity_count: int = 0
    selected_count: int = 0
    booked_count: int = 0
    percent: int = 0


class NextItem(TravelCrewModel):
    """The next thing that happens on this trip."""

    kind: str
    title: str
    starts_at: datetime | None = None
    starts_on: date | None = None
    source: str = "MOCK"


class TripCard(TravelCrewModel):
    """One journey, as the dashboard lists it."""

    trip_id: str
    bucket: TripBucket = "draft"
    origin: str | None = None
    destination: str | None = None
    departure_date: date | None = None
    return_date: date | None = None
    nights: int | None = None
    travelers: int = 1
    status: str = "draft"
    review_status: str = "pending"
    preferred_language: LanguageCode = "en"
    # None when the trip has no dates, and negative once it has departed -
    # both are different from "starts today" and the interface renders them so.
    days_until_departure: int | None = None
    budget: BudgetProgress = Field(default_factory=BudgetProgress)
    booking: BookingProgress = Field(default_factory=BookingProgress)
    next_item: NextItem | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DashboardCounts(TravelCrewModel):
    upcoming: int = 0
    drafts: int = 0
    past: int = 0
    total: int = 0


class DashboardResponse(TravelCrewModel):
    """Everything the dashboard renders, in one answer."""

    # Null for a visitor who has not signed in. Anonymous planning still works,
    # and the dashboard still shows that browser session's journeys.
    user: UserOut | None = None
    anonymous: bool = True

    counts: DashboardCounts = Field(default_factory=DashboardCounts)
    upcoming: list[TripCard] = Field(default_factory=list)
    drafts: list[TripCard] = Field(default_factory=list)
    past: list[TripCard] = Field(default_factory=list)

    # Populated in a later phase. Present now so the dashboard's shape does not
    # change under the interface when they arrive.
    price_watches: list[dict] = Field(default_factory=list)
    notifications: list[dict] = Field(default_factory=list)

    generated_at: datetime | None = None
