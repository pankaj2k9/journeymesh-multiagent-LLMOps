"""Trip preferences, trip budgets and the append-only budget ledger.

Additive. Nothing here alters an existing column: a trip with no preference row
falls back to a brief derived from its own fields, and a trip with no budget
row gets one created on first read.

Money is ``NUMERIC(14, 4)``. Four decimal places rather than two so that a fare
divided across three travellers multiplies back exactly; presentation rounds to
the currency's own precision.

Revision ID: 0003_preferences_budget
Revises: 0002_identity
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_preferences_budget"
down_revision = "0002_identity"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(precision=14, scale=4)


def _money(name: str, *, nullable: bool = False, default: str = "0") -> sa.Column:
    return sa.Column(
        name,
        sa.Numeric(precision=14, scale=4),
        nullable=nullable,
        server_default=None if nullable else sa.text(default),
    )


def upgrade() -> None:
    op.create_table(
        "trip_preferences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trip_id", sa.String(length=36), nullable=False),
        # ---- who ---------------------------------------------------------
        sa.Column("adults", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("children", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("child_ages", JSONB, nullable=False, server_default="[]"),
        # ---- when --------------------------------------------------------
        sa.Column("flexible_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "flexible_destination", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        # ---- flying ------------------------------------------------------
        sa.Column(
            "cabin_class", sa.String(length=24), nullable=False, server_default="economy"
        ),
        sa.Column("max_stops", sa.Integer(), nullable=True),
        sa.Column("baggage", sa.String(length=16), nullable=False, server_default="cabin_only"),
        sa.Column("preferred_airlines", JSONB, nullable=False, server_default="[]"),
        sa.Column("excluded_airlines", JSONB, nullable=False, server_default="[]"),
        sa.Column("earliest_departure_hour", sa.Integer(), nullable=True),
        sa.Column("latest_arrival_hour", sa.Integer(), nullable=True),
        # ---- staying -----------------------------------------------------
        sa.Column(
            "accommodation_type", sa.String(length=24), nullable=False, server_default="any"
        ),
        sa.Column("hotel_min_rating", sa.Float(), nullable=True),
        # ---- doing -------------------------------------------------------
        sa.Column("pace", sa.String(length=16), nullable=False, server_default="balanced"),
        sa.Column("interests", JSONB, nullable=False, server_default="[]"),
        sa.Column("dietary_requirements", sa.Text(), nullable=True),
        sa.Column("accessibility_requirements", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
    )
    # One brief per trip. A unique index rather than a unique constraint plus a
    # separate index, because that is what the model declares and two shapes
    # for one rule is how a schema starts drifting from its code.
    op.create_index(
        "ix_trip_preferences_trip_id", "trip_preferences", ["trip_id"], unique=True
    )

    op.create_table(
        "trip_budgets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trip_id", sa.String(length=36), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("total_budget", MONEY, nullable=True),
        _money("emergency_reserve"),
        # Derived totals by commitment strength. Every one of these is a cache
        # over budget_items; BudgetEngine.recompute is the only writer.
        _money("committed_cost"),
        _money("planned_cost"),
        _money("estimated_cost"),
        # Derived totals by category, for the budget dashboard.
        _money("flight_cost"),
        _money("accommodation_cost"),
        _money("activity_cost"),
        _money("local_transport_cost"),
        _money("food_estimate"),
        _money("miscellaneous_estimate"),
        # Optimistic lock: two concurrent selections cannot both read the same
        # remaining balance and both write their own total over it.
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "recomputed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
    )
    op.create_index("ix_trip_budgets_trip_id", "trip_budgets", ["trip_id"], unique=True)

    op.create_table(
        "budget_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trip_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="ESTIMATED"),
        sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
        _money("amount"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        # LIVE, CACHED, SEARCH_DERIVED, ESTIMATE, MOCK. A line that is not from
        # a payable source may never be counted as committed.
        sa.Column("source", sa.String(length=24), nullable=False, server_default="ESTIMATE"),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_by", sa.String(length=48), nullable=False, server_default="budget_engine"
        ),
        # A correction is a new row pointing back at the one it cancels, never
        # an edit. That is what makes the ledger auditable.
        sa.Column("reverses_id", sa.String(length=36), nullable=True),
        sa.Column("detail", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reverses_id"], ["budget_items.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_budget_items_trip_id", "budget_items", ["trip_id"])
    op.create_index("ix_budget_items_category", "budget_items", ["category"])
    op.create_index("ix_budget_items_state", "budget_items", ["state"])
    op.create_index("ix_budget_items_source_id", "budget_items", ["source_id"])
    op.create_index("ix_budget_items_reverses_id", "budget_items", ["reverses_id"])
    op.create_index(
        "ix_budget_items_trip_created",
        "budget_items",
        ["trip_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_budget_items_trip_state", "budget_items", ["trip_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_budget_items_trip_state", table_name="budget_items")
    op.drop_index("ix_budget_items_trip_created", table_name="budget_items")
    op.drop_index("ix_budget_items_reverses_id", table_name="budget_items")
    op.drop_index("ix_budget_items_source_id", table_name="budget_items")
    op.drop_index("ix_budget_items_state", table_name="budget_items")
    op.drop_index("ix_budget_items_category", table_name="budget_items")
    op.drop_index("ix_budget_items_trip_id", table_name="budget_items")
    op.drop_table("budget_items")

    op.drop_index("ix_trip_budgets_trip_id", table_name="trip_budgets")
    op.drop_table("trip_budgets")

    op.drop_index("ix_trip_preferences_trip_id", table_name="trip_preferences")
    op.drop_table("trip_preferences")
