"""Accounts, traveller profiles and trip ownership.

Additive only. ``trips.user_id`` is nullable, so every journey planned before
this migration keeps working exactly as it did and anonymous planning stays a
supported way to use the application.

Revision ID: 0002_identity
Revises: 0001_initial
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_identity"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="USER"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column(
            "preferred_language", sa.String(length=2), nullable=False, server_default="en"
        ),
        sa.Column(
            "preferred_currency", sa.String(length=3), nullable=False, server_default="USD"
        ),
        # Bumped to strand every token issued before a password change or a
        # forced sign-out, which is why there is no token blocklist table.
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "traveler_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column(
            "traveler_type", sa.String(length=16), nullable=False, server_default="ADULT"
        ),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("passport_country", sa.String(length=2), nullable=True),
        sa.Column("dietary_requirements", sa.Text(), nullable=True),
        sa.Column("accessibility_requirements", sa.Text(), nullable=True),
        sa.Column(
            "loyalty_programmes",
            sa.JSON().with_variant(
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
            server_default="{}",
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "full_name", name="uq_traveler_user_name"),
    )
    op.create_index("ix_traveler_profiles_user_id", "traveler_profiles", ["user_id"])

    # Nullable, and SET NULL rather than CASCADE: deleting an account must not
    # silently delete the journeys attached to it.
    op.add_column("trips", sa.Column("user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_trips_user_id", "trips", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_trips_user_id", "trips", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_trips_user_id", table_name="trips")
    op.drop_constraint("fk_trips_user_id", "trips", type_="foreignkey")
    op.drop_column("trips", "user_id")

    op.drop_index("ix_traveler_profiles_user_id", table_name="traveler_profiles")
    op.drop_table("traveler_profiles")

    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
