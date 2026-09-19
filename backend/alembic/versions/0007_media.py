"""Uploaded media metadata.

The bytes live on a persistent volume; this table holds only the metadata and
the relative path. Storing images as blobs would put megabytes of pixels into
every backup, every replica and every query plan, and make the database the
thing that has to scale with the media library.

Revision ID: 0007_media
Revises: 0006_currency
Create Date: 2026-09-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_media"
down_revision = "0006_currency"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # Generated from a UUID, a category and a date - never from the
        # uploaded filename, which is kept below for display only.
        sa.Column("relative_path", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "original_filename", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="blog"),
        sa.Column(
            "mime_type", sa.String(length=64), nullable=False, server_default="image/webp"
        ),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("derivatives", JSONB, nullable=False, server_default="{}"),
        sa.Column("uploaded_by", sa.String(length=36), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
    )
    # One row per stored file.
    op.create_index(
        "ix_media_assets_relative_path", "media_assets", ["relative_path"], unique=True
    )
    op.create_index("ix_media_assets_category", "media_assets", ["category"])
    op.create_index("ix_media_assets_uploaded_by", "media_assets", ["uploaded_by"])
    op.create_index(
        "ix_media_assets_created_at", "media_assets", [sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("ix_media_assets_created_at", table_name="media_assets")
    op.drop_index("ix_media_assets_uploaded_by", table_name="media_assets")
    op.drop_index("ix_media_assets_category", table_name="media_assets")
    op.drop_index("ix_media_assets_relative_path", table_name="media_assets")
    op.drop_table("media_assets")
