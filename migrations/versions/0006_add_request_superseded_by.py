"""add request superseded_by column

Revision ID: 0006_add_request_superseded_by
Revises: 0005_add_request_resolved_references
Create Date: 2026-03-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_add_request_superseded_by"
down_revision = "0005_add_request_resolved_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("superseded_by", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "superseded_by")
