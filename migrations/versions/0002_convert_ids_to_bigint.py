"""convert chatops ids to bigint

Revision ID: 0002_convert_ids_to_bigint
Revises: 0001_initial_chatops_tables
Create Date: 2026-03-22 00:00:00.000000
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa
from sonyflake import SonyFlake


revision = "0002_convert_ids_to_bigint"
down_revision = "0001_initial_chatops_tables"
branch_labels = None
depends_on = None


def _build_generator() -> SonyFlake:
    machine_id = int(os.getenv("SONYFLAKE_MACHINE_ID", "0"))
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    return SonyFlake(
        machine_id=lambda: machine_id,
        start_time=datetime(
            year=now_kst.year,
            month=now_kst.month,
            day=now_kst.day,
            tzinfo=kst,
        ),
    )


def _copy_rows_to_bigint_tables(bind) -> None:
    metadata = sa.MetaData()
    generator = _build_generator()

    sessions = sa.Table("sessions", metadata, autoload_with=bind)
    requests = sa.Table("requests", metadata, autoload_with=bind)
    request_events = sa.Table("request_events", metadata, autoload_with=bind)

    session_rows = bind.execute(sa.select(sessions)).mappings().all()
    request_rows = bind.execute(sa.select(requests)).mappings().all()
    event_rows = bind.execute(
        sa.select(request_events).order_by(request_events.c.request_id.asc(), request_events.c.sequence.asc())
    ).mappings().all()

    sessions_new = sa.Table("sessions_new", sa.MetaData(), autoload_with=bind)
    requests_new = sa.Table("requests_new", sa.MetaData(), autoload_with=bind)
    request_events_new = sa.Table("request_events_new", sa.MetaData(), autoload_with=bind)

    session_id_map: dict[object, int] = {}
    request_id_map: dict[object, int] = {}

    if session_rows:
        new_session_rows = []
        for row in session_rows:
            new_id = generator.next_id()
            session_id_map[row["id"]] = new_id
            new_session_rows.append(
                {
                    "id": new_id,
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        bind.execute(sessions_new.insert(), new_session_rows)

    if request_rows:
        new_request_rows = []
        for row in request_rows:
            new_id = generator.next_id()
            request_id_map[row["id"]] = new_id
            new_request_rows.append(
                {
                    "id": new_id,
                    "session_id": session_id_map[row["session_id"]],
                    "user_id": row["user_id"],
                    "message_text": row["message_text"],
                    "request_type": row["request_type"],
                    "status": row["status"],
                    "requires_approval": row["requires_approval"],
                    "final_response": row["final_response"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        bind.execute(requests_new.insert(), new_request_rows)

    if event_rows:
        new_event_rows = []
        for row in event_rows:
            new_event_rows.append(
                {
                    "id": generator.next_id(),
                    "request_id": request_id_map[row["request_id"]],
                    "session_id": session_id_map[row["session_id"]],
                    "sequence": row["sequence"],
                    "event_type": row["event_type"],
                    "payload": row["payload"],
                    "created_at": row["created_at"],
                }
            )
        bind.execute(request_events_new.insert(), new_event_rows)


def _copy_rows_to_string_tables(bind) -> None:
    metadata = sa.MetaData()

    sessions = sa.Table("sessions", metadata, autoload_with=bind)
    requests = sa.Table("requests", metadata, autoload_with=bind)
    request_events = sa.Table("request_events", metadata, autoload_with=bind)

    session_rows = bind.execute(sa.select(sessions)).mappings().all()
    request_rows = bind.execute(sa.select(requests)).mappings().all()
    event_rows = bind.execute(
        sa.select(request_events).order_by(request_events.c.request_id.asc(), request_events.c.sequence.asc())
    ).mappings().all()

    sessions_old = sa.Table("sessions_old", sa.MetaData(), autoload_with=bind)
    requests_old = sa.Table("requests_old", sa.MetaData(), autoload_with=bind)
    request_events_old = sa.Table("request_events_old", sa.MetaData(), autoload_with=bind)

    if session_rows:
        bind.execute(
            sessions_old.insert(),
            [
                {
                    "id": str(row["id"]),
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in session_rows
            ],
        )

    if request_rows:
        bind.execute(
            requests_old.insert(),
            [
                {
                    "id": str(row["id"]),
                    "session_id": str(row["session_id"]),
                    "user_id": row["user_id"],
                    "message_text": row["message_text"],
                    "request_type": row["request_type"],
                    "status": row["status"],
                    "requires_approval": row["requires_approval"],
                    "final_response": row["final_response"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in request_rows
            ],
        )

    if event_rows:
        bind.execute(
            request_events_old.insert(),
            [
                {
                    "id": str(row["id"]),
                    "request_id": str(row["request_id"]),
                    "session_id": str(row["session_id"]),
                    "sequence": row["sequence"],
                    "event_type": row["event_type"],
                    "payload": row["payload"],
                    "created_at": row["created_at"],
                }
                for row in event_rows
            ],
        )


def _drop_old_tables() -> None:
    op.drop_table("request_events")
    op.drop_table("requests")
    op.drop_table("sessions")


def _create_bigint_tables() -> None:
    op.create_table(
        "sessions_new",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "requests_new",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("sessions_new.id"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("final_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "request_events_new",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("request_id", sa.BigInteger(), sa.ForeignKey("requests_new.id"), nullable=False),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("sessions_new.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "sequence", name="uq_request_events_new_request_id_sequence"),
    )


def _create_string_tables() -> None:
    op.create_table(
        "sessions_old",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "requests_old",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions_old.id"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("final_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "request_events_old",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=36), sa.ForeignKey("requests_old.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions_old.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "sequence", name="uq_request_events_old_request_id_sequence"),
    )


def _rename_bigint_tables() -> None:
    op.rename_table("sessions_new", "sessions")
    op.rename_table("requests_new", "requests")
    op.rename_table("request_events_new", "request_events")

    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_requests_session_id", "requests", ["session_id"])
    op.create_index("ix_requests_user_id", "requests", ["user_id"])
    op.create_index("ix_request_events_request_id", "request_events", ["request_id"])
    op.create_index("ix_request_events_session_id", "request_events", ["session_id"])


def _rename_string_tables() -> None:
    op.rename_table("sessions_old", "sessions")
    op.rename_table("requests_old", "requests")
    op.rename_table("request_events_old", "request_events")

    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_requests_session_id", "requests", ["session_id"])
    op.create_index("ix_requests_user_id", "requests", ["user_id"])
    op.create_index("ix_request_events_request_id", "request_events", ["request_id"])
    op.create_index("ix_request_events_session_id", "request_events", ["session_id"])


def upgrade() -> None:
    bind = op.get_bind()
    _create_bigint_tables()
    _copy_rows_to_bigint_tables(bind)
    _drop_old_tables()
    _rename_bigint_tables()


def downgrade() -> None:
    bind = op.get_bind()
    _create_string_tables()
    _copy_rows_to_string_tables(bind)
    _drop_old_tables()
    _rename_string_tables()
