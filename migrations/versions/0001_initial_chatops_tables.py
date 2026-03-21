"""initial chatops tables

Revision ID: 0001_initial_chatops_tables
Revises:
Create Date: 2026-03-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_chatops_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("final_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_requests_session_id", "requests", ["session_id"])
    op.create_index("ix_requests_user_id", "requests", ["user_id"])

    op.create_table(
        "request_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=36), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "sequence", name="uq_request_events_request_id_sequence"),
    )
    op.create_index("ix_request_events_request_id", "request_events", ["request_id"])
    op.create_index("ix_request_events_session_id", "request_events", ["session_id"])


def downgrade() -> None:
    with op.batch_alter_table("request_events") as batch_op:
        batch_op.drop_constraint(
            "uq_request_events_request_id_sequence",
            type_="unique",
        )
    op.drop_index("ix_request_events_session_id", table_name="request_events")
    op.drop_index("ix_request_events_request_id", table_name="request_events")
    op.drop_table("request_events")

    op.drop_index("ix_requests_user_id", table_name="requests")
    op.drop_index("ix_requests_session_id", table_name="requests")
    op.drop_table("requests")

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
