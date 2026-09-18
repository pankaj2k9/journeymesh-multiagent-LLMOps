"""Foreign exchange: a rate cache, and the audit trail for converted money.

A journey is budgeted in one currency; its providers are not. A taka-budgeted
trip absorbs a dollar flight and a euro hotel, and this migration is what makes
that answerable rather than merely possible.

``budget_items`` gains the provider's own figure and the rate used to convert
it. Those columns are never overwritten: ``amount`` is what gets summed, in the
journey's currency, and ``original_amount``/``original_currency`` are what the
traveller will actually be charged. Without them, "why is this line 79,950
taka?" has no answer a month later.

``fx_rates`` is a cache with provenance, not a ledger. Rows are refreshed in
place; any rate that actually converted money has already been copied onto the
budget line that used it, where it is immutable.

Revision ID: 0006_currency
Revises: 0005_offers
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_currency"
down_revision = "0005_offers"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(precision=14, scale=4)
# Eight places: a rate rounded to four before it multiplies puts the error in
# the traveller's total rather than in the rate.
RATE = sa.Numeric(precision=20, scale=8)


def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", RATE, nullable=False),
        sa.Column(
            "provider", sa.String(length=48), nullable=False, server_default="offline_table"
        ),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="MOCK"),
        # The date the provider says the rate is for, which is not the moment
        # it was fetched: the ECB publishes once a working day.
        sa.Column("rate_date", sa.Date(), nullable=True),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_fx_rates_base_currency", "fx_rates", ["base_currency"])
    op.create_index("ix_fx_rates_quote_currency", "fx_rates", ["quote_currency"])
    # One row per pair; the cache is refreshed in place rather than appended to.
    op.create_index(
        "ix_fx_rates_pair", "fx_rates", ["base_currency", "quote_currency"], unique=True
    )

    # All nullable: the common line needs no conversion, and every row written
    # before this migration was already in the journey's own currency.
    op.add_column("budget_items", sa.Column("original_amount", MONEY, nullable=True))
    op.add_column(
        "budget_items", sa.Column("original_currency", sa.String(length=3), nullable=True)
    )
    op.add_column("budget_items", sa.Column("exchange_rate", RATE, nullable=True))
    op.add_column(
        "budget_items",
        sa.Column("exchange_rate_source", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "budget_items",
        sa.Column("exchange_rate_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("budget_items", "exchange_rate_at")
    op.drop_column("budget_items", "exchange_rate_source")
    op.drop_column("budget_items", "exchange_rate")
    op.drop_column("budget_items", "original_currency")
    op.drop_column("budget_items", "original_amount")

    op.drop_index("ix_fx_rates_pair", table_name="fx_rates")
    op.drop_index("ix_fx_rates_quote_currency", table_name="fx_rates")
    op.drop_index("ix_fx_rates_base_currency", table_name="fx_rates")
    op.drop_table("fx_rates")
