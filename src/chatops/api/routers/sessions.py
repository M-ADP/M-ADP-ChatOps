from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from chatops.api.dependencies import get_auth_context, get_db_session
from chatops.db.repositories import SessionRepository
from chatops.schemas.auth import AuthContext
from chatops.schemas.sessions import CreateSessionRequest, SessionResponse


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: CreateSessionRequest,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> SessionResponse:
    record = SessionRepository(db_session).create(user_id=auth.user_id, title=payload.title)
    return SessionResponse(
        session_id=record.id,
        user_id=record.user_id,
        title=record.title,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> SessionResponse:
    record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return SessionResponse(
        session_id=record.id,
        user_id=record.user_id,
        title=record.title,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
