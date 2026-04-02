"""add request resolved_references column

Revision ID: 0005_add_request_resolved_references
Revises: 0004_add_request_effective_message_text
Create Date: 2026-03-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_add_request_resolved_references"
down_revision = "0004_add_request_effective_message_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("resolved_references", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "resolved_references")
