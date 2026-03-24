"""add request missing_inputs column

Revision ID: 0003_add_request_missing_inputs
Revises: 0002_convert_ids_to_bigint
Create Date: 2026-03-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_add_request_missing_inputs"
down_revision = "0002_convert_ids_to_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("missing_inputs", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "missing_inputs")
