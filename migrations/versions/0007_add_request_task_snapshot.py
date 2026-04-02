"""add request task_snapshot column

Revision ID: 0007_add_request_task_snapshot
Revises: 0006_add_request_superseded_by
Create Date: 2026-04-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_add_request_task_snapshot"
down_revision = "0006_add_request_superseded_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("task_snapshot", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "task_snapshot")
