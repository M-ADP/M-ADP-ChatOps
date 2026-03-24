"""add request effective_message_text column

Revision ID: 0004_add_request_effective_message_text
Revises: 0003_add_request_missing_inputs
Create Date: 2026-03-24 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_add_request_effective_message_text"
down_revision = "0003_add_request_missing_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("effective_message_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "effective_message_text")
