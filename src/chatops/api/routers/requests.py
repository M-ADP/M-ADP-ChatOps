from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from chatops.api.dependencies import get_auth_context, get_db_session, get_graph_service
from chatops.db.models import RequestRecord
from chatops.db.repositories import RequestRepository, SessionRepository
from chatops.graph.service import GraphService
from chatops.schemas.auth import AuthContext
from chatops.schemas.requests import (
    ApproveRequestResponse,
    CreateRequestRequest,
    RejectRequestResponse,
    RequestResponse,
)
from chatops.services.events import EventService


router = APIRouter(prefix="/sessions/{session_id}/requests", tags=["requests"])


def _load_request_or_404(db_session: Session, request_id: str, user_id: str) -> RequestRecord:
    record = RequestRepository(db_session).get_for_user(request_id=request_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return record


@router.post("", response_model=RequestResponse, status_code=status.HTTP_202_ACCEPTED)
def create_request(
    session_id: str,
    payload: CreateRequestRequest,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
    graph_service: GraphService = Depends(get_graph_service),
) -> RequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    graph_result = graph_service.handle_request(
        session_id=session_id,
        user_id=auth.user_id,
        message_text=payload.message,
    )
    repo = RequestRepository(db_session)
    record = repo.create(
        session_id=session_id,
        user_id=auth.user_id,
        message_text=payload.message,
        request_type=graph_result.request_type,
        requires_approval=graph_result.requires_approval,
    )
    record.status = graph_result.status
    record.final_response = graph_result.final_response
    db_session.commit()
    db_session.refresh(record)
    event_service = EventService(db_session)
    event_service.append_event(
        request_id=record.id,
        session_id=record.session_id,
        event_type="request.created",
        payload={
            "type": "request.created",
            "request_id": record.id,
            "session_id": record.session_id,
            "status": record.status,
        },
    )
    if record.status == "pending_approval":
        event_service.append_event(
            request_id=record.id,
            session_id=record.session_id,
            event_type="approval.required",
            payload={
                "type": "approval.required",
                "request_id": record.id,
                "session_id": record.session_id,
                "status": record.status,
                "final_response": record.final_response,
            },
        )
    else:
        event_service.append_event(
            request_id=record.id,
            session_id=record.session_id,
            event_type="response.completed",
            payload={
                "type": "response.completed",
                "request_id": record.id,
                "session_id": record.session_id,
                "status": record.status,
                "final_response": record.final_response,
            },
        )

    return RequestResponse(
        request_id=record.id,
        session_id=record.session_id,
        status=record.status,
        message=record.message_text,
        request_type=record.request_type,
        requires_approval=record.requires_approval,
        final_response=record.final_response,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/{request_id}", response_model=RequestResponse)
def get_request(
    session_id: str,
    request_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> RequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    record = _load_request_or_404(db_session, request_id=request_id, user_id=auth.user_id)
    return RequestResponse(
        request_id=record.id,
        session_id=record.session_id,
        status=record.status,
        message=record.message_text,
        request_type=record.request_type,
        requires_approval=record.requires_approval,
        final_response=record.final_response,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("/{request_id}/approve", response_model=ApproveRequestResponse)
def approve_request(
    session_id: str,
    request_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
    graph_service: GraphService = Depends(get_graph_service),
) -> ApproveRequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    repo = RequestRepository(db_session)
    record = _load_request_or_404(db_session, request_id=request_id, user_id=auth.user_id)
    if record.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request is not pending approval")

    graph_result = graph_service.resume_request(
        request_id=request_id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=record.message_text,
    )
    record.status = graph_result.status
    record.final_response = graph_result.final_response
    record.requires_approval = graph_result.requires_approval
    db_session.commit()
    db_session.refresh(record)
    EventService(db_session).append_event(
        request_id=record.id,
        session_id=record.session_id,
        event_type="execution.completed" if record.status == "completed" else "execution.failed",
        payload={
            "type": "execution.completed" if record.status == "completed" else "execution.failed",
            "request_id": record.id,
            "session_id": record.session_id,
            "status": record.status,
            "final_response": record.final_response,
        },
    )
    updated = record
    return ApproveRequestResponse(request_id=updated.id, status=updated.status)


@router.post("/{request_id}/reject", response_model=RejectRequestResponse)
def reject_request(
    session_id: str,
    request_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> RejectRequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    repo = RequestRepository(db_session)
    record = _load_request_or_404(db_session, request_id=request_id, user_id=auth.user_id)
    if record.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request is not pending approval")

    updated = repo.update_status(request_id=request_id, status="rejected")
    EventService(db_session).append_event(
        request_id=updated.id,
        session_id=updated.session_id,
        event_type="approval.rejected",
        payload={
            "type": "approval.rejected",
            "request_id": updated.id,
            "session_id": updated.session_id,
            "status": updated.status,
        },
    )
    return RejectRequestResponse(request_id=updated.id, status=updated.status)
