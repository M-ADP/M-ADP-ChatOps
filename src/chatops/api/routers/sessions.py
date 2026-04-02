from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from chatops.api.dependencies import get_auth_context, get_db_session, get_graph_service
from chatops.api.routers.requests import create_request as create_request_resource
from chatops.db.repositories import MessageRepository, RequestRepository, SessionRepository
from chatops.graph.service import GraphService
from chatops.schemas.auth import AuthContext
from chatops.schemas.messages import (
    CreateSessionMessageRequest,
    CreateSessionMessageResponse,
    SessionMessagesPageResponse,
)
from chatops.schemas.requests import CreateRequestRequest
from chatops.schemas.sessions import (
    CreateSessionRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)
from chatops.services.session_messages import SessionMessageService


router = APIRouter(prefix="/sessions", tags=["sessions"])


def _build_session_response(record) -> SessionResponse:
    return SessionResponse(
        session_id=record.id,
        user_id=record.user_id,
        title=record.title,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: CreateSessionRequest,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> SessionResponse:
    record = SessionRepository(db_session).create(user_id=auth.user_id, title=payload.title)
    return _build_session_response(record)


@router.get("", response_model=SessionListResponse)
def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> SessionListResponse:
    session_repo = SessionRepository(db_session)
    sessions = session_repo.list_for_user(user_id=auth.user_id)
    message_repo = MessageRepository(db_session)
    messages = message_repo.list_for_sessions([record.id for record in sessions], auth.user_id)
    service = SessionMessageService()
    grouped_messages = service.group_by_session(messages)
    request_repo = RequestRepository(db_session)
    for session in sessions:
        if session.id in grouped_messages:
            continue
        grouped_messages[session.id] = service.synthesize_messages_from_requests(
            request_repo.list_for_session(session_id=session.id, user_id=auth.user_id)
        )
    return service.build_session_list(
        sessions,
        grouped_messages,
        limit=limit,
        cursor=cursor,
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> SessionDetailResponse:
    record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    service = SessionMessageService()
    message_repo = MessageRepository(db_session)
    records = message_repo.list_for_session(session_id=session_id, user_id=auth.user_id)
    messages = (
        [service.build_message(record) for record in records]
        if records
        else service.synthesize_messages_from_requests(
            RequestRepository(db_session).list_for_session(session_id=session_id, user_id=auth.user_id)
        )
    )
    page = service.paginate_messages(
        messages,
        limit=limit,
        before=None,
    )
    return SessionDetailResponse(
        session=_build_session_response(record),
        messages=page.messages,
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{session_id}/messages", response_model=SessionMessagesPageResponse)
def get_session_messages(
    session_id: int,
    before: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> SessionMessagesPageResponse:
    record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    service = SessionMessageService()
    message_repo = MessageRepository(db_session)
    records = message_repo.list_for_session(session_id=session_id, user_id=auth.user_id)
    messages = (
        [service.build_message(record) for record in records]
        if records
        else service.synthesize_messages_from_requests(
            RequestRepository(db_session).list_for_session(session_id=session_id, user_id=auth.user_id)
        )
    )
    return service.paginate_messages(
        messages,
        limit=limit,
        before=before,
    )


@router.post("/{session_id}/messages", response_model=CreateSessionMessageResponse, status_code=status.HTTP_202_ACCEPTED)
def post_session_message(
    session_id: int,
    payload: CreateSessionMessageRequest,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
    graph_service: GraphService = Depends(get_graph_service),
) -> CreateSessionMessageResponse:
    create_request_resource(
        session_id=session_id,
        payload=CreateRequestRequest(message=payload.message),
        auth=auth,
        db_session=db_session,
        graph_service=graph_service,
    )
    service = SessionMessageService()
    messages = MessageRepository(db_session).list_recent_for_session(
        session_id=session_id,
        user_id=auth.user_id,
        limit=2,
    )
    return CreateSessionMessageResponse(
        messages=[service.build_message(record) for record in messages],
    )
