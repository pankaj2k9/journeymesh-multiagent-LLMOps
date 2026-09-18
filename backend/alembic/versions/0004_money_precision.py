"""Give the planning budget the same precision as every other amount.

``trips.budget`` has been a ``double precision`` since the first migration.
That was harmless while it was only ever displayed, and stops being harmless
now that ``BudgetEngine`` seeds a real budget from it: a value stored as
2999.9999999999995 becomes a ceiling that a 3000.00 plan is over.

The conversion is exact in this direction - every value already in the column
came from a JSON number with at most two decimal places - and rounding to four
places makes that explicit rather than trusting the cast.

Revision ID: 0004_money_precision
Revises: 0003_preferences_budget
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_money_precision"
down_revision = "0003_preferences_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "trips",
        "budget",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=14, scale=4),
        existing_nullable=True,
        postgresql_using="round(budget::numeric, 4)",
    )


def downgrade() -> None:
    op.alter_column(
        "trips",
        "budget",
        existing_type=sa.Numeric(precision=14, scale=4),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="budget::double precision",
    )
