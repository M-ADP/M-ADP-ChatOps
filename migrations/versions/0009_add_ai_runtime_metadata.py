"""add ai runtime metadata

Revision ID: 0009_add_ai_runtime_metadata
Revises: 0008_add_messages_table
Create Date: 2026-04-03 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_add_ai_runtime_metadata"
down_revision = "0008_add_messages_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("session_summary", sa.Text(), nullable=True))
    op.add_column("requests", sa.Column("plan_object", sa.Text(), nullable=True))
    op.add_column("requests", sa.Column("verifier_decision", sa.Text(), nullable=True))
    op.add_column("requests", sa.Column("specialist_result", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("plan_object", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("verifier_decision", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("specialist_result", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "specialist_result")
    op.drop_column("messages", "verifier_decision")
    op.drop_column("messages", "plan_object")
    op.drop_column("requests", "specialist_result")
    op.drop_column("requests", "verifier_decision")
    op.drop_column("requests", "plan_object")
    op.drop_column("sessions", "session_summary")
