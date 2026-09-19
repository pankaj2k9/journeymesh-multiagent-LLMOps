"""Tourist attractions shown beside the cities in the planner.

Revision ID: 0008_attractions
Revises: 0007_media
Create Date: 2026-09-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_attractions"
down_revision = "0007_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attractions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wikipedia_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("image_media_id", sa.String(length=36), nullable=True),
        sa.Column("image_author", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("image_license", sa.String(length=80), nullable=False, server_default=""),
        sa.Column(
            "image_license_url", sa.String(length=500), nullable=False, server_default=""
        ),
        sa.Column(
            "image_source_url", sa.String(length=500), nullable=False, server_default=""
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.ForeignKeyConstraint(["image_media_id"], ["media_assets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_attractions_slug", "attractions", ["slug"], unique=True)
    op.create_index("ix_attractions_city", "attractions", ["city"])
    op.create_index("ix_attractions_country", "attractions", ["country"])
    op.create_index("ix_attractions_image_media_id", "attractions", ["image_media_id"])
    op.create_index("ix_attractions_is_active", "attractions", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_attractions_is_active", table_name="attractions")
    op.drop_index("ix_attractions_image_media_id", table_name="attractions")
    op.drop_index("ix_attractions_country", table_name="attractions")
    op.drop_index("ix_attractions_city", table_name="attractions")
    op.drop_index("ix_attractions_slug", table_name="attractions")
    op.drop_table("attractions")
