from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from chatops.api.dependencies import get_auth_context, get_db_session
from chatops.db.repositories import RequestRepository, SessionRepository
from chatops.schemas.auth import AuthContext
from chatops.services.events import EventService


router = APIRouter(prefix="/sessions/{session_id}/requests", tags=["stream"])


def _format_sse_body(events) -> str:
    chunks: list[str] = []
    for event in events:
        chunks.append(f"id: {event.sequence}\n")
        chunks.append(f"event: {event.event_type}\n")
        chunks.append(f"data: {event.payload}\n\n")
    return "".join(chunks)


@router.get("/{request_id}/stream")
def stream_request(
    session_id: int,
    request_id: int,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> Response:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    request_record = RequestRepository(db_session).get_for_user(request_id=request_id, user_id=auth.user_id)
    if request_record is None or request_record.session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    sequence = int(last_event_id or 0)
    events = EventService(db_session).list_after_sequence(request_id=request_id, sequence=sequence)
    return Response(content=_format_sse_body(events), media_type="text/event-stream")
