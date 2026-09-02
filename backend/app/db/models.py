"""SQLAlchemy models backing JourneyMesh persistence."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on PostgreSQL, plain JSON everywhere else (the SQLite fallback).
JSONType = JSON().with_variant(JSONB, "postgresql")


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

    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str | None] = mapped_column(String(120))
    destination: Mapped[str | None] = mapped_column(String(120))
    departure_date: Mapped[date | None] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date)
    travelers: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[float | None] = mapped_column(Float)
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


Index("ix_trips_created_at", Trip.created_at.desc())
Index("ix_audit_events_created_at", AuditEvent.created_at.desc())
