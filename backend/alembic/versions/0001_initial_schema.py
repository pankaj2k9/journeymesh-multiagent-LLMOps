"""Initial JourneyMesh schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=120), nullable=True),
        sa.Column("destination", sa.String(length=120), nullable=True),
        sa.Column("departure_date", sa.Date(), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("travelers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("travel_style", sa.String(length=32), nullable=True),
        sa.Column("hotel_preference", sa.String(length=32), nullable=True),
        sa.Column("interests", JSONB, nullable=True),
        sa.Column("special_requirements", sa.Text(), nullable=True),
        sa.Column("additional_instructions", sa.Text(), nullable=True),
        sa.Column("preferred_language", sa.String(length=2), nullable=False, server_default="en"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("revision_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("constraints", JSONB, nullable=True),
        sa.Column("selected_agents", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_trips_session_id", "trips", ["session_id"])
    op.create_index("ix_trips_status", "trips", ["status"])
    op.create_index("ix_trips_created_at", "trips", [sa.text("created_at DESC")])

    op.create_table(
        "travel_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "trip_id",
            sa.String(length=36),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("flight_results", JSONB, nullable=True),
        sa.Column("hotel_results", JSONB, nullable=True),
        sa.Column("weather_results", JSONB, nullable=True),
        sa.Column("budget_analysis", JSONB, nullable=True),
        sa.Column("itinerary", JSONB, nullable=True),
        sa.Column("final_summary", JSONB, nullable=True),
        sa.Column("provider_metadata", JSONB, nullable=True),
        sa.Column("evaluation_summary", JSONB, nullable=True),
        sa.Column("guardrail_summary", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_travel_results_trip_id", "travel_results", ["trip_id"])

    op.create_table(
        "human_reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "trip_id",
            sa.String(length=36),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "review_status", sa.String(length=32), nullable=False, server_default="awaiting_review"
        ),
        sa.Column("requested_changes", sa.Text(), nullable=True),
        sa.Column("selected_agents", JSONB, nullable=True),
        sa.Column("change_scope", JSONB, nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_human_reviews_trip_id", "human_reviews", ["trip_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "trip_id",
            sa.String(length=36),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=False, server_default="system"),
        sa.Column("agent", sa.String(length=48), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_conversation_messages_trip_id", "conversation_messages", ["trip_id"])
    op.create_index("ix_conversation_messages_session_id", "conversation_messages", ["session_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "trip_id",
            sa.String(length=36),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("actor", sa.String(length=48), nullable=True),
        sa.Column("detail", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_audit_events_trip_id", "audit_events", ["trip_id"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_created_at", "audit_events", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("conversation_messages")
    op.drop_table("human_reviews")
    op.drop_table("travel_results")
    op.drop_table("trips")
