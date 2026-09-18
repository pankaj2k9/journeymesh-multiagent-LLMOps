"""Search runs, normalised offers and traveller selections.

Additive. One ``offers`` table serves flights, hotels and activities: they
share every column anything outside the adapter layer reads, and differ only in
the shape of ``payload``. Three near-identical tables would mean three of every
query and three code paths through the budget.

Offer rows are snapshots and are never updated to a newer price. A changed
price is a new row, so what a traveller was shown at the moment they chose
stays recoverable.

Revision ID: 0005_offers
Revises: 0004_money_precision
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_offers"
down_revision = "0004_money_precision"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(precision=14, scale=4)


def upgrade() -> None:
    op.create_table(
        "search_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trip_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="MOCK"),
        sa.Column("cache_key", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("criteria", JSONB, nullable=False, server_default="{}"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_search_runs_trip_id", "search_runs", ["trip_id"])
    op.create_index("ix_search_runs_user_id", "search_runs", ["user_id"])
    op.create_index("ix_search_runs_session_id", "search_runs", ["session_id"])
    op.create_index("ix_search_runs_kind", "search_runs", ["kind"])
    op.create_index("ix_search_runs_cache_key", "search_runs", ["cache_key"])
    op.create_index("ix_search_runs_trip_kind", "search_runs", ["trip_id", "kind"])
    op.create_index(
        "ix_search_runs_created_at", "search_runs", [sa.text("created_at DESC")]
    )

    op.create_table(
        "offers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("offer_ref", sa.String(length=160), nullable=False),
        sa.Column("search_id", sa.String(length=36), nullable=True),
        sa.Column("trip_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="MOCK"),
        # Denormalised for sorting and the admin view; the authoritative copy
        # lives inside payload.
        sa.Column("total_amount", MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["search_id"], ["search_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_offers_offer_ref", "offers", ["offer_ref"])
    op.create_index("ix_offers_search_id", "offers", ["search_id"])
    op.create_index("ix_offers_trip_id", "offers", ["trip_id"])
    op.create_index("ix_offers_kind", "offers", ["kind"])
    op.create_index("ix_offers_source", "offers", ["source"])
    op.create_index("ix_offers_trip_kind", "offers", ["trip_id", "kind"])

    op.create_table(
        "selected_offers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trip_id", sa.String(length=36), nullable=False),
        sa.Column("offer_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        # The budget line this selection created, so deselecting reverses
        # exactly the money the selection added.
        sa.Column("budget_item_id", sa.String(length=36), nullable=True),
        sa.Column("travelers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_amount", MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="SELECTED"),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("selected_by", sa.String(length=48), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_selected_offers_trip_id", "selected_offers", ["trip_id"])
    op.create_index("ix_selected_offers_offer_id", "selected_offers", ["offer_id"])
    op.create_index("ix_selected_offers_kind", "selected_offers", ["kind"])
    op.create_index("ix_selected_offers_status", "selected_offers", ["status"])
    op.create_index("ix_selected_offers_budget_item_id", "selected_offers", ["budget_item_id"])
    op.create_index(
        "ix_selected_offers_trip_kind_status",
        "selected_offers",
        ["trip_id", "kind", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_selected_offers_trip_kind_status", table_name="selected_offers")
    op.drop_index("ix_selected_offers_budget_item_id", table_name="selected_offers")
    op.drop_index("ix_selected_offers_status", table_name="selected_offers")
    op.drop_index("ix_selected_offers_kind", table_name="selected_offers")
    op.drop_index("ix_selected_offers_offer_id", table_name="selected_offers")
    op.drop_index("ix_selected_offers_trip_id", table_name="selected_offers")
    op.drop_table("selected_offers")

    op.drop_index("ix_offers_trip_kind", table_name="offers")
    op.drop_index("ix_offers_source", table_name="offers")
    op.drop_index("ix_offers_kind", table_name="offers")
    op.drop_index("ix_offers_trip_id", table_name="offers")
    op.drop_index("ix_offers_search_id", table_name="offers")
    op.drop_index("ix_offers_offer_ref", table_name="offers")
    op.drop_table("offers")

    op.drop_index("ix_search_runs_created_at", table_name="search_runs")
    op.drop_index("ix_search_runs_trip_kind", table_name="search_runs")
    op.drop_index("ix_search_runs_cache_key", table_name="search_runs")
    op.drop_index("ix_search_runs_kind", table_name="search_runs")
    op.drop_index("ix_search_runs_session_id", table_name="search_runs")
    op.drop_index("ix_search_runs_user_id", table_name="search_runs")
    op.drop_index("ix_search_runs_trip_id", table_name="search_runs")
    op.drop_table("search_runs")
