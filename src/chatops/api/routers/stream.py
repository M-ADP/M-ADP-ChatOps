from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from chatops.api.dependencies import get_auth_context, get_db_session
from chatops.common.logging.audit import AuditRoute
from chatops.common.config.settings import get_app_config
from chatops.db.models import RequestRecord
from chatops.db.repositories import RequestRepository, SessionRepository
from chatops.domain.enums import RequestStatus
from chatops.schemas.auth import AuthContext
from chatops.services.events import EventService


router = APIRouter(prefix="/sessions/{session_id}/requests", tags=["stream"], route_class=AuditRoute)


def _format_sse_body(events) -> str:
    chunks: list[str] = []
    for event in events:
        chunks.append(f"id: {event.sequence}\n")
        chunks.append(f"event: {event.event_type}\n")
        chunks.append(f"data: {event.payload}\n\n")
    return "".join(chunks)


def _is_terminal_status(raw_status: str | None) -> bool:
    if raw_status is None:
        return False
    try:
        return RequestStatus(raw_status).is_terminal
    except ValueError:
        return False


def _stream_follow_events(
    session_factory: sessionmaker[Session],
    request_id: int,
    starting_sequence: int,
    keepalive_seconds: int,
    poll_interval_seconds: float = 0.1,
):
    last_sequence = starting_sequence
    last_emitted_at = time.monotonic()

    while True:
        with session_factory() as poll_session:
            request_record = poll_session.get(RequestRecord, request_id)
            events = EventService(poll_session).list_after_sequence(request_id=request_id, sequence=last_sequence)

        if events:
            yield _format_sse_body(events)
            last_sequence = events[-1].sequence
            last_emitted_at = time.monotonic()
            if _is_terminal_status(request_record.status if request_record else None):
                break
            continue

        if _is_terminal_status(request_record.status if request_record else None):
            break

        now = time.monotonic()
        if now - last_emitted_at >= keepalive_seconds:
            yield ": keep-alive\n\n"
            last_emitted_at = now
        time.sleep(poll_interval_seconds)


@router.get("/{request_id}/stream")
def stream_request(
    session_id: int,
    request_id: int,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    follow: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> Response:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    request_record = RequestRepository(db_session).get_for_user(request_id=request_id, user_id=auth.user_id)
    if request_record is None or request_record.session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    _SSE_HEADERS = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }

    sequence = int(last_event_id or 0)
    if not follow:
        events = EventService(db_session).list_after_sequence(request_id=request_id, sequence=sequence)
        return Response(content=_format_sse_body(events), media_type="text/event-stream", headers=_SSE_HEADERS)

    session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        future=True,
    )
    app_config = get_app_config()
    return StreamingResponse(
        _stream_follow_events(
            session_factory=session_factory,
            request_id=request_id,
            starting_sequence=sequence,
            keepalive_seconds=app_config.request_stream_keepalive_seconds,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
