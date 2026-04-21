"""add projects table

Revision ID: 0010_add_projects_table
Revises: 0009_add_ai_runtime_metadata
Create Date: 2026-04-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_add_projects_table"
down_revision = "0009_add_ai_runtime_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.add_column(
        "sessions",
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id"), nullable=True),
    )
    op.create_index("ix_sessions_project_id", "sessions", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_project_id", table_name="sessions")
    op.drop_column("sessions", "project_id")

    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
