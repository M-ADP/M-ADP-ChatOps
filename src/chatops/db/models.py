from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from chatops.common.id_generator import IdGenerator
from chatops.db.base import Base
from chatops.domain.enums import RequestStatus, RequestType, SessionStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=IdGenerator.generate_sonyflake_id)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=SessionStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )


class RequestRecord(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=IdGenerator.generate_sonyflake_id)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    message_text: Mapped[str] = mapped_column(Text())
    effective_message_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    request_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=RequestStatus.CREATED.value)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    missing_inputs: Mapped[str | None] = mapped_column(Text(), nullable=True)
    final_response: Mapped[str | None] = mapped_column(Text(), nullable=True)
    resolved_references: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )


class RequestEventRecord(Base):
    __tablename__ = "request_events"
    __table_args__ = (UniqueConstraint("request_id", "sequence", name="uq_request_events_request_id_sequence"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=IdGenerator.generate_sonyflake_id)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
