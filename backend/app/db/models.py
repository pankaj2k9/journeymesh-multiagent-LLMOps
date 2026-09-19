"""SQLAlchemy models backing Travel Crew AI persistence."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.constants import (
    ITEM_ESTIMATED,
    ROLE_USER,
    USER_ACTIVE,
)
from app.db.types import JSONType, MoneyColumn


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Trip(Base):
    """One planned journey."""

    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # Nullable on purpose. Anonymous planning still works exactly as it did,
    # and `POST /auth/claim-session` moves those trips onto an account later.
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str | None] = mapped_column(String(120))
    destination: Mapped[str | None] = mapped_column(String(120))
    departure_date: Mapped[date | None] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date)
    travelers: Mapped[int] = mapped_column(Integer, default=1)
    # The planning ceiling. Exact, because BudgetEngine seeds a real budget
    # from it and a float ceiling of 2999.9999999999995 makes a 3000.00 plan
    # look over budget.
    budget: Mapped[Decimal | None] = mapped_column(MoneyColumn)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    travel_style: Mapped[str | None] = mapped_column(String(32))
    hotel_preference: Mapped[str | None] = mapped_column(String(32))
    interests: Mapped[list[str]] = mapped_column(JSONType, default=list)
    special_requirements: Mapped[str | None] = mapped_column(Text)
    additional_instructions: Mapped[str | None] = mapped_column(Text)
    preferred_language: Mapped[str] = mapped_column(String(2), default="en")

    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    revision_count: Mapped[int] = mapped_column(Integer, default=1)

    constraints: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    selected_agents: Mapped[list[str]] = mapped_column(JSONType, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    result: Mapped[TravelResult | None] = relationship(
        back_populates="trip", cascade="all, delete-orphan", uselist=False
    )
    reviews: Mapped[list[HumanReview]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="HumanReview.revision_number"
    )
    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="ConversationMessage.created_at"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    owner: Mapped[User | None] = relationship(back_populates="trips")
    preference: Mapped[TripPreference | None] = relationship(
        back_populates="trip", cascade="all, delete-orphan", uselist=False
    )
    budget_record: Mapped[TripBudget | None] = relationship(
        back_populates="trip", cascade="all, delete-orphan", uselist=False
    )
    budget_items: Mapped[list[BudgetItem]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="BudgetItem.created_at",
    )
    selections: Mapped[list[SelectedOffer]] = relationship(
        cascade="all, delete-orphan", order_by="SelectedOffer.created_at"
    )


class TravelResult(Base):
    """Agent output for a trip. One row per trip, updated on every revision."""

    __tablename__ = "travel_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), unique=True, index=True
    )

    flight_results: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    hotel_results: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    weather_results: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    budget_analysis: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    itinerary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    final_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    provider_metadata: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    evaluation_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    guardrail_summary: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    trip: Mapped[Trip] = relationship(back_populates="result")


class HumanReview(Base):
    """One row per human review decision."""

    __tablename__ = "human_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[str] = mapped_column(String(32), default="awaiting_review")
    requested_changes: Mapped[str | None] = mapped_column(Text)
    selected_agents: Mapped[list[str]] = mapped_column(JSONType, default=list)
    change_scope: Mapped[list[str]] = mapped_column(JSONType, default=list)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    trip: Mapped[Trip] = relationship(back_populates="reviews")


class ConversationMessage(Base):
    """Durable conversation trail (user turns and safe agent summaries)."""

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(24), default="system")
    agent: Mapped[str | None] = mapped_column(String(48))
    content: Mapped[str] = mapped_column(Text, default="")
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    trip: Mapped[Trip] = relationship(back_populates="messages")


class AuditEvent(Base):
    """Security and lifecycle audit trail. Never stores raw PII."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    actor: Mapped[str | None] = mapped_column(String(48))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    trip: Mapped[Trip | None] = relationship(back_populates="audit_events")



class User(Base):
    """A traveller account.

    Identity was optional in this application before bookings existed, and it
    stays optional: an anonymous session can plan a whole trip. An account is
    what makes a trip *ownable* - required before money, bookings or an admin
    view mean anything.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Stored lower-cased and unique; the service normalises before writing.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default=ROLE_USER, index=True)
    status: Mapped[str] = mapped_column(String(16), default=USER_ACTIVE, index=True)
    preferred_language: Mapped[str] = mapped_column(String(2), default="en")
    preferred_currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Bumped on password change and on logout-everywhere, so a refresh token
    # minted before the change stops validating without a token blocklist.
    token_version: Mapped[int] = mapped_column(Integer, default=1)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    trips: Mapped[list[Trip]] = relationship(back_populates="owner")
    travelers: Mapped[list[TravelerProfile]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class TravelerProfile(Base):
    """A person who travels - the account holder or someone they book for.

    Deliberately thin. Passport numbers and dates of birth are the kind of data
    a booking provider needs at the moment of purchase and that this database
    has no reason to hold, so only the country is stored here and the rest is
    collected at booking time.
    """

    __tablename__ = "traveler_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    traveler_type: Mapped[str] = mapped_column(String(16), default="ADULT")
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    passport_country: Mapped[str | None] = mapped_column(String(2))
    dietary_requirements: Mapped[str | None] = mapped_column(Text)
    accessibility_requirements: Mapped[str | None] = mapped_column(Text)
    loyalty_programmes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped[User] = relationship(back_populates="travelers")


class TripPreference(Base):
    """The structured search brief for one trip.

    Separate from ``trips`` rather than thirty more columns on it: these are
    the inputs a *search* takes, they change independently of the trip's
    lifecycle, and keeping them apart means a flight search reads one row
    instead of the whole planning record.
    """

    __tablename__ = "trip_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), unique=True, index=True
    )

    # ---- who is going ---------------------------------------------------
    adults: Mapped[int] = mapped_column(Integer, default=1)
    children: Mapped[int] = mapped_column(Integer, default=0)
    # Ages at the time of travel; fare rules and hotel occupancy both need them.
    child_ages: Mapped[list[int]] = mapped_column(JSONType, default=list)

    # ---- when -----------------------------------------------------------
    # A flexible search shifts both dates by up to this many days.
    flexible_days: Mapped[int] = mapped_column(Integer, default=0)
    flexible_destination: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---- flying ---------------------------------------------------------
    cabin_class: Mapped[str] = mapped_column(String(24), default="economy")
    max_stops: Mapped[int | None] = mapped_column(Integer)
    baggage: Mapped[str] = mapped_column(String(16), default="cabin_only")
    preferred_airlines: Mapped[list[str]] = mapped_column(JSONType, default=list)
    excluded_airlines: Mapped[list[str]] = mapped_column(JSONType, default=list)
    earliest_departure_hour: Mapped[int | None] = mapped_column(Integer)
    latest_arrival_hour: Mapped[int | None] = mapped_column(Integer)

    # ---- staying --------------------------------------------------------
    accommodation_type: Mapped[str] = mapped_column(String(24), default="any")
    hotel_min_rating: Mapped[float | None] = mapped_column(Float)

    # ---- doing ----------------------------------------------------------
    pace: Mapped[str] = mapped_column(String(16), default="balanced")
    interests: Mapped[list[str]] = mapped_column(JSONType, default=list)
    dietary_requirements: Mapped[str | None] = mapped_column(Text)
    accessibility_requirements: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    trip: Mapped[Trip] = relationship(back_populates="preference")

    @property
    def travelers(self) -> int:
        return self.adults + self.children


class TripBudget(Base):
    """The cached totals for one trip's budget.

    Every column here is *derived* from ``budget_items``; none of it is a
    source of truth. It exists so a dashboard can render a budget without
    summing a ledger, and ``BudgetEngine.recompute`` is the only writer.
    ``version`` makes that write optimistically locked, so two concurrent
    selections cannot both read 4000 and both write 2164.
    """

    __tablename__ = "trip_budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), unique=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    total_budget: Mapped[Decimal | None] = mapped_column(MoneyColumn)
    emergency_reserve: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))

    # Derived totals, by commitment strength.
    committed_cost: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    planned_cost: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    estimated_cost: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))

    # Derived totals, by category. Denormalised for the budget dashboard.
    flight_cost: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    accommodation_cost: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    activity_cost: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    local_transport_cost: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    food_estimate: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    miscellaneous_estimate: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))

    version: Mapped[int] = mapped_column(Integer, default=1)
    recomputed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    trip: Mapped[Trip] = relationship(back_populates="budget_record")


class BudgetItem(Base):
    """One line of the budget ledger. Append-only.

    Nothing in this table is ever edited or deleted to correct a mistake: a
    correction is a new row whose ``reverses_id`` points at the original and
    whose amount is its negation. That is what makes "Museum removed -$80"
    something the interface can show and an auditor can verify, rather than a
    number that quietly changed.
    """

    __tablename__ = "budget_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )

    category: Mapped[str] = mapped_column(String(24), index=True)
    state: Mapped[str] = mapped_column(String(16), default=ITEM_ESTIMATED, index=True)
    label: Mapped[str] = mapped_column(String(200), default="")

    # Always in the trip's base currency - this is the number that is summed.
    amount: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # What the provider actually quoted, before conversion, and the rate used.
    # Never overwritten: this is what a traveller will really be charged, and
    # it is the only way to answer "why is this line this many taka?" later.
    # Null when no conversion happened, which is the common case.
    original_amount: Mapped[Decimal | None] = mapped_column(MoneyColumn)
    original_currency: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    exchange_rate_source: Mapped[str | None] = mapped_column(String(24))
    exchange_rate_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Where the number came from: LIVE, CACHED, ESTIMATE, MOCK. A line that is
    # not from a payable source may never be counted as committed.
    source: Mapped[str] = mapped_column(String(24), default="ESTIMATE")

    # What this line is attached to, if anything: a selected offer, a booking,
    # or nothing at all for a manually entered expense.
    source_type: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # Who put it there: "budget_engine", "user", or an agent name. An agent may
    # only ever produce an ESTIMATED line.
    created_by: Mapped[str] = mapped_column(String(48), default="budget_engine")

    reverses_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("budget_items.id", ondelete="SET NULL"), index=True
    )
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    trip: Mapped[Trip] = relationship(back_populates="budget_items")



class SearchRun(Base):
    """One execution of one search, kept so results can be re-read.

    A search is persisted rather than held in a request because everything
    afterwards refers back to it: the offer a traveller selects an hour later,
    the price watch built from the same criteria, the admin view of what was
    searched today, and the evaluation suite asking whether the cheapest option
    was actually recommended.

    ``criteria`` is stored as the validated JSON of the criteria model, so a
    replay uses exactly what the provider was asked, not a reconstruction.
    """

    __tablename__ = "search_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)

    kind: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[str] = mapped_column(String(48), default="")
    source: Mapped[str] = mapped_column(String(24), default="MOCK")
    # Stable identity of the criteria, so a repeat search is recognisable.
    cache_key: Mapped[str] = mapped_column(String(400), default="", index=True)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    result_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    offers: Mapped[list[Offer]] = relationship(
        back_populates="search", cascade="all, delete-orphan"
    )


class Offer(Base):
    """One normalised offer, exactly as it was shown to the traveller.

    A single table for flights, hotels and activities. They share every column
    that anything outside the adapter layer reads - price, currency, provider,
    source, expiry - and differ only in the shape of ``payload``, which is the
    serialised ``FlightOffer`` / ``HotelOffer`` / ``ActivityOffer``. Three
    near-identical tables would mean three of every query, three joins on
    selections and three code paths through the budget.

    The row is a *snapshot*. It is never updated to a newer price: a changed
    price is a new offer, so what a traveller was shown when they chose remains
    recoverable - which is exactly what a price-change dispute needs.
    """

    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # The provider-scoped identifier carried on the offer itself.
    offer_ref: Mapped[str] = mapped_column(String(160), index=True)
    search_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("search_runs.id", ondelete="CASCADE"), index=True
    )
    trip_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[str] = mapped_column(String(48), default="")
    source: Mapped[str] = mapped_column(String(24), default="MOCK", index=True)

    # Denormalised for sorting and for the admin view. The authoritative copy
    # is inside `payload`; these exist so a list query does not parse JSON.
    total_amount: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    title: Mapped[str] = mapped_column(String(200), default="")

    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    search: Mapped[SearchRun | None] = relationship(back_populates="offers")


class SelectedOffer(Base):
    """An offer a traveller has chosen for a trip, before any booking exists.

    Selection is a real state with real consequences - it moves the budget -
    and it is not a booking. Keeping it in its own table means the budget can
    show "planned" money separately from "committed" money, and a traveller can
    change their mind without anything having to be cancelled.

    Superseded rows are kept rather than deleted, so the sequence of choices
    stays visible next to the budget ledger that mirrors it.
    """

    __tablename__ = "selected_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    offer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)

    # The budget line this selection created, so deselecting reverses exactly
    # the money the selection added.
    budget_item_id: Mapped[str | None] = mapped_column(String(36), index=True)

    travelers: Mapped[int] = mapped_column(Integer, default=1)
    total_amount: Mapped[Decimal] = mapped_column(MoneyColumn, default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    status: Mapped[str] = mapped_column(String(24), default="SELECTED", index=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36))
    selected_by: Mapped[str | None] = mapped_column(String(48))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    offer: Mapped[Offer] = relationship()



class FxRate(Base):
    """A cached foreign-exchange rate.

    Rates are quoted against one base (the euro, because that is what the ECB
    publishes), so a single daily fetch serves every pair by cross-rate. The
    table is a cache with provenance, not a ledger: rows are replaced as they
    are refreshed, and any rate actually used to convert money is copied onto
    the budget line that used it, where it is immutable.
    """

    __tablename__ = "fx_rates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), index=True)
    # Units of quote_currency per one base_currency. Eight decimal places: a
    # rate rounded to four before it multiplies puts the error in the
    # traveller's total rather than in the rate.
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 8))

    provider: Mapped[str] = mapped_column(String(48), default="offline_table")
    source: Mapped[str] = mapped_column(String(24), default="MOCK")
    # The date the provider says the rate is for, which is not the moment we
    # fetched it - ECB reference rates are published once a day.
    rate_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)



class MediaAsset(Base):
    """One uploaded file. The bytes live on a volume; this row is the metadata.

    Deliberately not a blob column. PostgreSQL would happily store the image,
    and then every backup, every replica and every query plan would carry
    megabytes of pixels that a filesystem serves better - and the database
    would become the thing that must scale with the media library.

    ``relative_path`` is the only identity. The public URL is derived from it
    at read time, so moving from a local disk to a CDN changes one setting
    rather than every row.
    """

    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Generated, never taken from the upload. See media/storage.py.
    relative_path: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    # Kept for display only. It is never used to build a path.
    original_filename: Mapped[str] = mapped_column(String(255), default="")

    category: Mapped[str] = mapped_column(String(32), default="blog", index=True)
    mime_type: Mapped[str] = mapped_column(String(64), default="image/webp")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)

    # Required for accessibility and read by search engines. Empty is allowed
    # on upload and prompted for in the media library.
    alt_text: Mapped[str] = mapped_column(String(300), default="")
    title: Mapped[str | None] = mapped_column(String(200))

    # {"small": {"path": ..., "width": ..., "height": ...}, ...}
    derivatives: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Incremented as the asset is attached to a post or a destination, so the
    # media library can warn before deleting something still in use.
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )



class Attraction(Base):
    """A place worth visiting, shown beside the cities in the planner.

    Seeded from ``app/db/seed_data/attractions.json`` and editable afterwards:
    the seed only ever inserts, so an administrator's changes survive a
    redeploy. The photograph is a media-library asset, so it can be replaced
    from the admin panel like any other image; its author and licence are kept
    here because free licences require the credit to travel with the picture.
    """

    __tablename__ = "attractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120), index=True)
    country: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    wikipedia_url: Mapped[str] = mapped_column(String(500), default="")

    image_media_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="SET NULL"), index=True
    )
    image_author: Mapped[str] = mapped_column(String(200), default="")
    image_license: Mapped[str] = mapped_column(String(80), default="")
    image_license_url: Mapped[str] = mapped_column(String(500), default="")
    image_source_url: Mapped[str] = mapped_column(String(500), default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    image: Mapped[MediaAsset | None] = relationship(lazy="joined")

Index("ix_trips_created_at", Trip.created_at.desc())
Index("ix_audit_events_created_at", AuditEvent.created_at.desc())
Index("ix_budget_items_trip_created", BudgetItem.trip_id, BudgetItem.created_at.desc())
Index("ix_budget_items_trip_state", BudgetItem.trip_id, BudgetItem.state)
Index("ix_offers_trip_kind", Offer.trip_id, Offer.kind)
# One row per pair. The cache is refreshed in place rather than appended to.
Index("ix_fx_rates_pair", FxRate.base_currency, FxRate.quote_currency, unique=True)
Index("ix_media_assets_created_at", MediaAsset.created_at.desc())
Index("ix_search_runs_trip_kind", SearchRun.trip_id, SearchRun.kind)
Index("ix_search_runs_created_at", SearchRun.created_at.desc())

# One live selection per kind per trip. Superseded rows keep the history, so
# the constraint is enforced in the service rather than by a partial index,
# which SQLite could not mirror for the test suite.
Index("ix_selected_offers_trip_kind_status", SelectedOffer.trip_id, SelectedOffer.kind, SelectedOffer.status)

# One traveller profile per name per account; re-adding "Ayesha Rahman" twice
# is a mistake, not a second person.
UniqueConstraint(
    TravelerProfile.user_id, TravelerProfile.full_name, name="uq_traveler_user_name"
)
