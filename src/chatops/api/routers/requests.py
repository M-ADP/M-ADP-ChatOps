from __future__ import annotations

import json

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
from chatops.services.approval_intent import ApprovalIntent, detect_approval_intent
from chatops.services.events import EventService


router = APIRouter(prefix="/sessions/{session_id}/requests", tags=["requests"])


def _dump_missing_inputs(missing_inputs: list[str] | None) -> str | None:
    if not missing_inputs:
        return None
    return json.dumps(missing_inputs, ensure_ascii=False)


def _load_missing_inputs(raw_value: str | None) -> list[str] | None:
    if not raw_value:
        return None
    try:
        loaded = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, list):
        return None
    return [str(item) for item in loaded]


def _dump_json_field(value: dict | list | None) -> str | None:
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False)


def _load_json_field(raw_value: str | None) -> dict | list | None:
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return None


def _load_request_or_404(db_session: Session, request_id: int, user_id: str) -> RequestRecord:
    record = RequestRepository(db_session).get_for_user(request_id=request_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return record


@router.post("", response_model=RequestResponse, status_code=status.HTTP_202_ACCEPTED)
def create_request(
    session_id: int,
    payload: CreateRequestRequest,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
    graph_service: GraphService = Depends(get_graph_service),
) -> RequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    repo = RequestRepository(db_session)
    previous_request = repo.get_latest_for_session(session_id=session_id, user_id=auth.user_id)
    session_context = None
    if previous_request is not None:
        session_context = {
            "last_message_text": previous_request.message_text,
            "last_effective_message_text": previous_request.effective_message_text,
            "last_request_status": previous_request.status,
            "last_request_type": previous_request.request_type,
            "last_missing_inputs": _load_missing_inputs(previous_request.missing_inputs),
            "last_final_response": previous_request.final_response,
            "last_resolved_references": _load_json_field(previous_request.resolved_references),
        }

    # 자연어 승인/거절: 이전 요청이 pending_approval이면 intent 감지
    if previous_request is not None and previous_request.status == "pending_approval":
        intent = detect_approval_intent(payload.message)
        if intent == ApprovalIntent.APPROVE:
            return _handle_natural_language_approval(
                previous_request=previous_request,
                message_text=payload.message,
                session_id=session_id,
                auth=auth,
                db_session=db_session,
                graph_service=graph_service,
            )
        if intent == ApprovalIntent.REJECT:
            return _handle_natural_language_rejection(
                previous_request=previous_request,
                message_text=payload.message,
                session_id=session_id,
                auth=auth,
                db_session=db_session,
                graph_service=graph_service,
            )
        # CORRECTION and UNKNOWN fall through to normal flow
        # CORRECTION will be handled by re-planning with corrected values in session context

    graph_result = graph_service.handle_request(
        session_id=session_id,
        user_id=auth.user_id,
        message_text=payload.message,
        user_role=auth.user_role,
        org_id=auth.org_id,
        session_context=session_context,
    )
    record = repo.create(
        request_id=graph_result.request_id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=payload.message,
        effective_message_text=graph_result.effective_message_text,
        request_type=graph_result.request_type,
        requires_approval=graph_result.requires_approval,
    )
    record.status = graph_result.status
    record.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    record.final_response = graph_result.final_response
    record.resolved_references = _dump_json_field(graph_result.resolved_references)
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
                "missing_inputs": _load_missing_inputs(record.missing_inputs),
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
        assistant_message=record.final_response,
        request_type=record.request_type,
        requires_approval=record.requires_approval,
        missing_inputs=_load_missing_inputs(record.missing_inputs),
        final_response=record.final_response,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _handle_natural_language_approval(
    previous_request: RequestRecord,
    message_text: str,
    session_id: int,
    auth: AuthContext,
    db_session: Session,
    graph_service: GraphService,
) -> RequestResponse:
    """Handle '응', '실행해' etc. as approval for the pending request."""
    graph_result = graph_service.resume_request(
        request_id=previous_request.id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=previous_request.message_text,
        approval_granted=True,
        user_role=auth.user_role,
        org_id=auth.org_id,
    )
    previous_request.status = graph_result.status
    previous_request.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    previous_request.final_response = graph_result.final_response
    previous_request.requires_approval = graph_result.requires_approval
    db_session.commit()
    db_session.refresh(previous_request)
    event_type = "execution.completed" if previous_request.status == "completed" else "execution.failed"
    EventService(db_session).append_event(
        request_id=previous_request.id,
        session_id=previous_request.session_id,
        event_type=event_type,
        payload={
            "type": event_type,
            "request_id": previous_request.id,
            "session_id": previous_request.session_id,
            "status": previous_request.status,
            "final_response": previous_request.final_response,
        },
    )
    return RequestResponse(
        request_id=previous_request.id,
        session_id=previous_request.session_id,
        status=previous_request.status,
        message=message_text,
        assistant_message=previous_request.final_response,
        request_type=previous_request.request_type,
        requires_approval=previous_request.requires_approval,
        missing_inputs=_load_missing_inputs(previous_request.missing_inputs),
        final_response=previous_request.final_response,
        created_at=previous_request.created_at,
        updated_at=previous_request.updated_at,
    )


def _handle_natural_language_rejection(
    previous_request: RequestRecord,
    message_text: str,
    session_id: int,
    auth: AuthContext,
    db_session: Session,
    graph_service: GraphService,
) -> RequestResponse:
    """Handle '아니', '취소해' etc. as rejection for the pending request."""
    graph_result = graph_service.resume_request(
        request_id=previous_request.id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=previous_request.message_text,
        approval_granted=False,
        user_role=auth.user_role,
        org_id=auth.org_id,
    )
    previous_request.status = graph_result.status
    previous_request.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    previous_request.final_response = graph_result.final_response
    previous_request.requires_approval = graph_result.requires_approval
    db_session.commit()
    db_session.refresh(previous_request)
    EventService(db_session).append_event(
        request_id=previous_request.id,
        session_id=previous_request.session_id,
        event_type="approval.rejected",
        payload={
            "type": "approval.rejected",
            "request_id": previous_request.id,
            "session_id": previous_request.session_id,
            "status": previous_request.status,
        },
    )
    return RequestResponse(
        request_id=previous_request.id,
        session_id=previous_request.session_id,
        status=previous_request.status,
        message=message_text,
        assistant_message=previous_request.final_response,
        request_type=previous_request.request_type,
        requires_approval=previous_request.requires_approval,
        missing_inputs=_load_missing_inputs(previous_request.missing_inputs),
        final_response=previous_request.final_response,
        created_at=previous_request.created_at,
        updated_at=previous_request.updated_at,
    )


@router.get("/{request_id}", response_model=RequestResponse)
def get_request(
    session_id: int,
    request_id: int,
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
        assistant_message=record.final_response,
        request_type=record.request_type,
        requires_approval=record.requires_approval,
        missing_inputs=_load_missing_inputs(record.missing_inputs),
        final_response=record.final_response,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("/{request_id}/approve", response_model=ApproveRequestResponse)
def approve_request(
    session_id: int,
    request_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
    graph_service: GraphService = Depends(get_graph_service),
) -> ApproveRequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    record = _load_request_or_404(db_session, request_id=request_id, user_id=auth.user_id)
    if record.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request is not pending approval")

    graph_result = graph_service.resume_request(
        request_id=request_id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=record.message_text,
        approval_granted=True,
        user_role=auth.user_role,
        org_id=auth.org_id,
    )
    record.status = graph_result.status
    record.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
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
    return ApproveRequestResponse(
        request_id=updated.id,
        status=updated.status,
        assistant_message=updated.final_response,
    )


@router.post("/{request_id}/reject", response_model=RejectRequestResponse)
def reject_request(
    session_id: int,
    request_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
    graph_service: GraphService = Depends(get_graph_service),
) -> RejectRequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    record = _load_request_or_404(db_session, request_id=request_id, user_id=auth.user_id)
    if record.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request is not pending approval")

    graph_result = graph_service.resume_request(
        request_id=request_id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=record.message_text,
        approval_granted=False,
        user_role=auth.user_role,
        org_id=auth.org_id,
    )
    record.status = graph_result.status
    record.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    record.final_response = graph_result.final_response
    record.requires_approval = graph_result.requires_approval
    db_session.commit()
    db_session.refresh(record)
    updated = record
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
    return RejectRequestResponse(
        request_id=updated.id,
        status=updated.status,
        assistant_message=updated.final_response,
    )
