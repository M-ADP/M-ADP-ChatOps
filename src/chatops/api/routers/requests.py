from __future__ import annotations

import json
import inspect
import logging
import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from chatops.api.dependencies import get_auth_context, get_db_session, get_graph_service
from chatops.common.logging.audit import AuditRoute
from chatops.common.id_generator import IdGenerator
from chatops.common.config.settings import get_app_config
from chatops.db.models import RequestRecord
from chatops.db.repositories import MessageRepository, RequestEventRepository, RequestRepository, SessionRepository
from chatops.domain.enums import RequestStatus
from chatops.graph.service import GraphService
from chatops.schemas.auth import AuthContext
from chatops.schemas.events import RequestEventListResponse, RequestEventResponse
from chatops.schemas.requests import (
    ApproveRequestRequest,
    ApproveRequestResponse,
    CreateRequestRequest,
    RejectRequestResponse,
    RequestListResponse,
    RequestResponse,
)
from chatops.services.approval_intent import ApprovalIntent, detect_approval_intent
from chatops.services.conversation_router import ConversationRouterService
from chatops.services.entity_memory_service import EntityMemoryService
from chatops.services.events import EventService
from chatops.services.follow_up_interpreter import FollowUpInterpreterService
from chatops.services.session_summary_service import SessionSummaryService
from chatops.services.session_messages import SessionMessageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions/{session_id}/requests", tags=["requests"], route_class=AuditRoute)
entity_memory_service = EntityMemoryService()
session_summary_service = SessionSummaryService()
follow_up_interpreter = FollowUpInterpreterService()
conversation_router = ConversationRouterService()


# ──────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────

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


def _load_task_snapshot(raw_value: str | None) -> dict | None:
    loaded = _load_json_field(raw_value)
    if isinstance(loaded, dict):
        return loaded
    return None


def _load_plan_object(raw_value: str | None) -> dict | None:
    loaded = _load_json_field(raw_value)
    if isinstance(loaded, dict):
        return loaded
    return None


def _load_verifier_decision(raw_value: str | None) -> dict | None:
    loaded = _load_json_field(raw_value)
    if isinstance(loaded, dict):
        return loaded
    return None


def _load_specialist_result(raw_value: str | None) -> dict | None:
    loaded = _load_json_field(raw_value)
    if isinstance(loaded, dict):
        return loaded
    return None


def _supports_parameter(func, parameter_name: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    return parameter_name in signature.parameters


def _build_session_factory(db_session: Session) -> sessionmaker[Session]:
    bind = db_session.get_bind()
    bind = getattr(bind, "engine", bind)
    return sessionmaker(
        bind=bind,
        autoflush=False,
        autocommit=False,
        future=True,
    )


def _response_delta_chunks(text: str | None) -> list[str]:
    if text is None:
        return []
    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    for piece in re.split(r"(?<=[.!?])\s+|(?<=요\.)\s+|(?<=다\.)\s+|(?<=까\?)\s+|(?<=요\?)\s+", normalized):
        trimmed = piece.strip()
        if not trimmed:
            continue
        if len(trimmed) <= 80:
            chunks.append(trimmed)
            continue
        for start in range(0, len(trimmed), 80):
            segment = trimmed[start:start + 80].strip()
            if segment:
                chunks.append(segment)
    return chunks


def _preview_request(
    graph_service: GraphService,
    *,
    message_text: str,
    session_context: dict[str, object] | None,
) -> dict[str, object] | None:
    preview = getattr(graph_service, "preview_request", None)
    if preview is None:
        return None
    return preview(message_text=message_text, session_context=session_context)


def _invoke_graph_handle_request(
    graph_service: GraphService,
    *,
    session_id: int,
    user_id: str,
    message_text: str,
    user_role: str | None,
    session_context: dict[str, object] | None,
    request_id: int | None = None,
    response_stream_handler=None,
):
    kwargs = {
        "session_id": session_id,
        "user_id": user_id,
        "message_text": message_text,
        "user_role": user_role,
        "session_context": session_context,
    }
    if request_id is not None and _supports_parameter(graph_service.handle_request, "request_id"):
        kwargs["request_id"] = request_id
    if response_stream_handler is not None and _supports_parameter(
        graph_service.handle_request, "response_stream_handler"
    ):
        kwargs["response_stream_handler"] = response_stream_handler
    return graph_service.handle_request(**kwargs)


def _build_request_response(record: RequestRecord, message_text: str) -> RequestResponse:
    return RequestResponse(
        request_id=record.id,
        session_id=record.session_id,
        status=record.status,
        message=message_text,
        assistant_message=record.final_response,
        request_type=record.request_type,
        requires_approval=record.requires_approval,
        missing_inputs=_load_missing_inputs(record.missing_inputs),
        final_response=record.final_response,
        task=_load_task_snapshot(record.task_snapshot),
        plan=_load_plan_object(record.plan_object),
        verifier=_load_verifier_decision(record.verifier_decision),
        specialist=_load_specialist_result(record.specialist_result),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _build_event_response(record) -> RequestEventResponse:
    payload = _load_json_field(record.payload)
    data = payload if isinstance(payload, dict) else {}
    event_type = data.get("type") if isinstance(data.get("type"), str) else record.event_type
    return RequestEventResponse(
        sequence=record.sequence,
        type=event_type,
        data=data,
        timestamp=record.created_at,
    )


def _append_user_message(
    db_session: Session,
    *,
    session_id: int,
    request_id: int,
    user_id: str,
    message_text: str,
) -> None:
    MessageRepository(db_session).create(
        session_id=session_id,
        request_id=request_id,
        user_id=user_id,
        role="user",
        message_type="text",
        text=message_text,
    )


def _sync_assistant_message(db_session: Session, record: RequestRecord) -> None:
    task_snapshot = record.task_snapshot
    message_type = "task" if task_snapshot else "text"
    text = SessionMessageService.assistant_text(record.final_response, task_snapshot)
    if text is None and task_snapshot is None:
        return
    MessageRepository(db_session).upsert_assistant_for_request(
        session_id=record.session_id,
        request_id=record.id,
        user_id=record.user_id,
        message_type=message_type,
        text=text,
        task_snapshot=task_snapshot,
        plan_object=record.plan_object,
        verifier_decision=record.verifier_decision,
        specialist_result=record.specialist_result,
    )


def _sync_session_summary(db_session: Session, *, session_id: int, user_id: str, session_summary: dict | None) -> None:
    SessionRepository(db_session).update_summary(
        session_id=session_id,
        user_id=user_id,
        session_summary=_dump_json_field(session_summary),
    )


def _load_request_or_404(db_session: Session, request_id: int, user_id: str) -> RequestRecord:
    record = RequestRepository(db_session).get_for_user(request_id=request_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return record


def _load_session_summary(
    db_session: Session,
    *,
    session_id: int,
    user_id: str,
) -> dict[str, object] | None:
    record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=user_id)
    if record is None:
        return None
    return session_summary_service.load(record.session_summary)


def _build_session_summary(
    *,
    db_session: Session,
    session_id: int,
    user_id: str,
    message_text: str,
    graph_result,
) -> dict[str, object] | None:
    if graph_result.session_summary:
        return graph_result.session_summary
    previous_summary = _load_session_summary(db_session, session_id=session_id, user_id=user_id)
    return session_summary_service.build(
        message_text=message_text,
        plan_object=graph_result.plan_object,
        task_snapshot=graph_result.task_snapshot,
        verifier_decision=graph_result.verifier_decision,
        resolved_references=graph_result.resolved_references,
        resolved_ids=graph_result.resolved_ids,
        previous_summary=previous_summary,
    )


def _expects_exact_name_confirmation(record: RequestRecord) -> bool:
    response = record.final_response or ""
    return "정확히 입력" in response


def _supersede_pending_request(record: RequestRecord, replacement_request_id: int | None = None) -> None:
    record.status = RequestStatus.SUPERSEDED.value
    record.superseded_by = replacement_request_id
    replacement_hint = ""
    if replacement_request_id is not None:
        replacement_hint = f" 최신 요청 ID는 {replacement_request_id}입니다."
    record.final_response = (
        "정정 요청으로 인해 이 승인 요청은 무효화되었습니다."
        f"{replacement_hint} 최신 요청만 승인할 수 있습니다."
    )


def _check_ttl(record: RequestRecord) -> None:
    """P0: 승인 TTL 만료 확인. 만료 시 상태 전이 없이 예외 발생."""
    if record.status != RequestStatus.PENDING_APPROVAL.value:
        return
    app_config = get_app_config()
    ttl_seconds = app_config.approval_ttl_seconds
    if record.created_at is None:
        return
    created = record.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    from datetime import timedelta
    if datetime.now(timezone.utc) > created + timedelta(seconds=ttl_seconds):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="요청이 만료되었습니다. 다시 요청해주세요.",
        )


def _atomic_status_transition(
    db_session: Session,
    request_id: int,
    from_status: str,
    to_status: str,
) -> bool:
    """P0: 원자적 상태 전이. Race condition 방지."""
    result = db_session.execute(
        update(RequestRecord)
        .where(
            RequestRecord.id == request_id,
            RequestRecord.status == from_status,
        )
        .values(status=to_status)
    )
    db_session.flush()
    return result.rowcount > 0


def _build_graph_audit_context(graph_result, user_id: str) -> dict[str, object]:
    audit_context = dict(graph_result.execution_audit or {})
    audit_context.setdefault("user_id", user_id)
    audit_context.setdefault("fallback_used", graph_result.fallback_used)
    audit_context.setdefault("clarification_type", graph_result.clarification_type)
    return audit_context


def _append_structured_event(
    event_service: EventService,
    *,
    request_id: int,
    session_id: int,
    event_type: str,
    phase: str,
    step: str,
    message: str,
    status_value: str | None = None,
    progress: int | None = None,
    payload: dict[str, object] | None = None,
    audit_context: dict[str, object] | None = None,
) -> None:
    event_payload: dict[str, object] = {
        "type": event_type,
        "phase": phase,
        "step": step,
        "message": message,
        "request_id": request_id,
        "session_id": session_id,
    }
    if status_value is not None:
        event_payload["status"] = status_value
    if progress is not None:
        event_payload["progress"] = progress
    if payload:
        event_payload.update({key: value for key, value in payload.items() if value is not None})

    if audit_context is None:
        event_service.append_event(
            request_id=request_id,
            session_id=session_id,
            event_type=event_type,
            payload=event_payload,
        )
        return

    event_service.append_audit_event(
        request_id=request_id,
        session_id=session_id,
        event_type=event_type,
        payload=event_payload,
        audit_context=audit_context,
    )


def _context_hydration_payload(session_context: dict[str, object] | None) -> dict[str, object]:
    entity_memory = session_context.get("entity_memory") if isinstance(session_context, dict) else {}
    request_trail = session_context.get("request_trail") if isinstance(session_context, dict) else []
    projects = entity_memory.get("projects", []) if isinstance(entity_memory, dict) else []
    applications = entity_memory.get("applications", []) if isinstance(entity_memory, dict) else []
    users = entity_memory.get("users", []) if isinstance(entity_memory, dict) else []

    return {
        "project_context_count": len(projects) if isinstance(projects, list) else 0,
        "application_context_count": len(applications) if isinstance(applications, list) else 0,
        "user_context_count": len(users) if isinstance(users, list) else 0,
        "request_trail_count": len(request_trail) if isinstance(request_trail, list) else 0,
    }


def _append_request_created_event(event_service: EventService, *, record: RequestRecord) -> None:
    _append_structured_event(
        event_service,
        request_id=record.id,
        session_id=record.session_id,
        event_type="request.created",
        phase="request",
        step="created",
        message="요청을 접수했습니다.",
        status_value=record.status,
        progress=10,
        payload={
            "request_type": record.request_type,
            "task": _load_task_snapshot(record.task_snapshot),
        },
    )


def _append_context_hydrated_event(
    event_service: EventService,
    *,
    record: RequestRecord,
    session_context: dict[str, object] | None,
) -> None:
    hydration_payload = _context_hydration_payload(session_context)
    hydration_payload["task"] = _load_task_snapshot(record.task_snapshot)

    _append_structured_event(
        event_service,
        request_id=record.id,
        session_id=record.session_id,
        event_type="context.hydrated",
        phase="planning",
        step="context_hydrated",
        message="세션 문맥을 반영했습니다.",
        status_value=record.status,
        progress=20,
        payload=hydration_payload,
    )


def _append_request_resolution_events(
    event_service: EventService,
    *,
    record: RequestRecord,
    graph_result,
    audit_context: dict[str, object],
    response_streamed: bool = False,
) -> None:
    _append_structured_event(
        event_service,
        request_id=record.id,
        session_id=record.session_id,
        event_type="parsing.completed",
        phase="planning",
        step="parsed",
        message="요청 해석을 마쳤습니다.",
        status_value=record.status,
        progress=40,
        payload={
            "request_type": record.request_type,
            "intent": graph_result.intent,
            "selected_operation_ids": graph_result.selected_operation_ids,
            "resolved_references": graph_result.resolved_references,
            "missing_inputs": _load_missing_inputs(record.missing_inputs),
            "task": _load_task_snapshot(record.task_snapshot),
        },
        audit_context=audit_context,
    )

    if not response_streamed:
        _append_supplemental_response_events(
            event_service,
            record=record,
            text=record.final_response,
            source="final_response",
            synthetic=True,
        )

    if record.status == RequestStatus.PENDING_APPROVAL.value:
        _append_structured_event(
            event_service,
            request_id=record.id,
            session_id=record.session_id,
            event_type="approval.required",
            phase="approval",
            step="required",
            message="승인이 필요합니다.",
            status_value=record.status,
            progress=80,
            payload={
                "final_response": record.final_response,
                "missing_inputs": _load_missing_inputs(record.missing_inputs),
                "task": _load_task_snapshot(record.task_snapshot),
            },
            audit_context=audit_context,
        )
        return

    if record.status == RequestStatus.AMBIGUOUS.value:
        _append_structured_event(
            event_service,
            request_id=record.id,
            session_id=record.session_id,
            event_type="request.ambiguous",
            phase="planning",
            step="ambiguous",
            message="후보가 여러 개라 추가 확인이 필요합니다.",
            status_value=record.status,
            progress=70,
            payload={"final_response": record.final_response, "task": _load_task_snapshot(record.task_snapshot)},
            audit_context=audit_context,
        )
        return

    if record.status == RequestStatus.INPUT_REQUIRED.value:
        _append_structured_event(
            event_service,
            request_id=record.id,
            session_id=record.session_id,
            event_type="request.input_required",
            phase="planning",
            step="input_required",
            message="추가 입력이 필요합니다.",
            status_value=record.status,
            progress=70,
            payload={
                "final_response": record.final_response,
                "missing_inputs": _load_missing_inputs(record.missing_inputs),
                "task": _load_task_snapshot(record.task_snapshot),
            },
            audit_context=audit_context,
        )
        return

    terminal_event_type = "request.failed" if record.status == RequestStatus.FAILED.value else "response.completed"
    terminal_message = "요청 처리에 실패했습니다." if record.status == RequestStatus.FAILED.value else "응답 생성을 마쳤습니다."
    _append_structured_event(
        event_service,
        request_id=record.id,
        session_id=record.session_id,
        event_type=terminal_event_type,
        phase="response",
        step="completed" if terminal_event_type == "response.completed" else "failed",
        message=terminal_message,
        status_value=record.status,
        progress=100,
        payload={"final_response": record.final_response, "task": _load_task_snapshot(record.task_snapshot)},
        audit_context=audit_context,
    )


def _append_request_lifecycle_events(
    event_service: EventService,
    *,
    record: RequestRecord,
    graph_result,
    session_context: dict[str, object] | None,
    audit_context: dict[str, object],
) -> None:
    _append_request_created_event(event_service, record=record)
    _append_context_hydrated_event(
        event_service,
        record=record,
        session_context=session_context,
    )
    _append_request_resolution_events(
        event_service,
        record=record,
        graph_result=graph_result,
        audit_context=audit_context,
    )


def _append_execution_started_event(event_service: EventService, record: RequestRecord) -> None:
    _append_structured_event(
        event_service,
        request_id=record.id,
        session_id=record.session_id,
        event_type="execution.started",
        phase="execution",
        step="started",
        message="승인된 요청 실행을 시작했습니다.",
        status_value=RequestStatus.EXECUTING.value,
        progress=85,
    )


def _append_execution_terminal_event(
    event_service: EventService,
    *,
    record: RequestRecord,
    graph_result,
    user_id: str,
) -> None:
    audit_context = _build_graph_audit_context(graph_result, user_id)
    event_type = "execution.completed" if record.status == RequestStatus.COMPLETED.value else "execution.failed"
    _append_structured_event(
        event_service,
        request_id=record.id,
        session_id=record.session_id,
        event_type=event_type,
        phase="execution",
        step="completed" if event_type == "execution.completed" else "failed",
        message="요청 실행을 마쳤습니다." if event_type == "execution.completed" else "요청 실행에 실패했습니다.",
        status_value=record.status,
        progress=100,
        payload={"final_response": record.final_response, "task": _load_task_snapshot(record.task_snapshot)},
        audit_context=audit_context,
    )


def _append_response_stream_start_event(event_service: EventService, *, record: RequestRecord) -> None:
    _append_structured_event(
        event_service,
        request_id=record.id,
        session_id=record.session_id,
        event_type="response.started",
        phase="response",
        step="started",
        message="AI 응답 생성을 시작했습니다.",
        status_value=RequestStatus.PROCESSING.value,
        progress=80,
    )


def _append_response_delta_event(
    event_service: EventService,
    *,
    record: RequestRecord,
    text: str,
    source: str = "model_stream",
    synthetic: bool = False,
) -> None:
    event_service.append_event(
        request_id=record.id,
        session_id=record.session_id,
        event_type="response.delta",
        payload={
            "type": "response.delta",
            "request_id": record.id,
            "session_id": record.session_id,
            "text": text,
            "source": source,
            "synthetic": synthetic,
        },
    )


def _append_supplemental_response_events(
    event_service: EventService,
    *,
    record: RequestRecord,
    text: str | None,
    source: str,
    synthetic: bool,
) -> None:
    chunks = _response_delta_chunks(text)
    if not chunks:
        return
    _append_response_stream_start_event(event_service, record=record)
    for chunk in chunks:
        _append_response_delta_event(
            event_service,
            record=record,
            text=chunk,
            source=source,
            synthetic=synthetic,
        )


def _process_async_request(
    *,
    session_factory: sessionmaker[Session],
    graph_service: GraphService,
    request_id: int,
    session_id: int,
    user_id: str,
    user_role: str | None,
    message_text: str,
    session_context: dict[str, object] | None,
) -> None:
    worker_session = session_factory()
    try:
        repo = RequestRepository(worker_session)
        record = repo.get_for_user(request_id=request_id, user_id=user_id)
        if record is None:
            return

        event_service = EventService(worker_session)
        stream_started = False

        def on_response_chunk(text: str) -> None:
            nonlocal stream_started
            if not text:
                return
            if not stream_started:
                _append_response_stream_start_event(event_service, record=record)
                stream_started = True
            _append_response_delta_event(
                event_service,
                record=record,
                text=text,
                source="model_stream",
                synthetic=False,
            )

        graph_result = _invoke_graph_handle_request(
            graph_service,
            session_id=session_id,
            user_id=user_id,
            message_text=message_text,
            user_role=user_role,
            session_context=session_context,
            request_id=request_id,
            response_stream_handler=on_response_chunk,
        )

        record = repo.get_for_user(request_id=request_id, user_id=user_id)
        if record is None:
            return

        record.status = graph_result.status
        record.request_type = graph_result.request_type
        record.requires_approval = graph_result.requires_approval
        record.effective_message_text = graph_result.effective_message_text
        record.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
        record.final_response = graph_result.final_response
        record.resolved_references = _dump_json_field(graph_result.resolved_references)
        record.task_snapshot = _dump_json_field(graph_result.task_snapshot)
        record.plan_object = _dump_json_field(graph_result.plan_object)
        record.verifier_decision = _dump_json_field(graph_result.verifier_decision)
        record.specialist_result = _dump_json_field(graph_result.specialist_result)
        worker_session.commit()
        worker_session.refresh(record)

        _sync_session_summary(
            worker_session,
            session_id=record.session_id,
            user_id=user_id,
            session_summary=_build_session_summary(
                db_session=worker_session,
                session_id=record.session_id,
                user_id=user_id,
                message_text=message_text,
                graph_result=graph_result,
            ),
        )
        _append_request_resolution_events(
            event_service,
            record=record,
            graph_result=graph_result,
            audit_context=_build_graph_audit_context(graph_result, user_id),
            response_streamed=stream_started,
        )
        _sync_assistant_message(worker_session, record)
    except Exception:
        logger.exception("Async request processing failed for request_id=%s", request_id)
        repo = RequestRepository(worker_session)
        record = repo.get_for_user(request_id=request_id, user_id=user_id)
        if record is not None and not RequestStatus(record.status).is_terminal:
            record.status = RequestStatus.FAILED.value
            record.final_response = "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            worker_session.commit()
            _append_structured_event(
                EventService(worker_session),
                request_id=record.id,
                session_id=record.session_id,
                event_type="request.failed",
                phase="response",
                step="failed",
                message="요청 처리에 실패했습니다.",
                status_value=record.status,
                progress=100,
                payload={"final_response": record.final_response},
            )
            _sync_assistant_message(worker_session, record)
    finally:
        worker_session.close()


# ──────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────

@router.get("", response_model=RequestListResponse)
def list_requests(
    session_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    request_status: str | None = Query(default=None, alias="status"),
    request_type_filter: str | None = Query(default=None, alias="request_type"),
    query_text: str | None = Query(default=None, alias="q"),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> RequestListResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    items, total = RequestRepository(db_session).list_page_for_session(
        session_id=session_id,
        user_id=auth.user_id,
        limit=limit,
        offset=offset,
        status=request_status,
        request_type=request_type_filter,
        query_text=query_text,
    )
    return RequestListResponse(
        items=[_build_request_response(record, record.message_text) for record in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}/events", response_model=RequestEventListResponse)
def list_request_events(
    session_id: int,
    request_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> RequestEventListResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    record = _load_request_or_404(db_session, request_id=request_id, user_id=auth.user_id)
    if record.session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    items, total = RequestEventRepository(db_session).list_for_request(
        request_id=request_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
        event_type=event_type,
    )
    return RequestEventListResponse(
        items=[_build_event_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )

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
    superseded_request: RequestRecord | None = None
    if previous_request is not None:
        session_context = {
            "last_message_text": previous_request.message_text,
            "last_effective_message_text": previous_request.effective_message_text,
            "last_request_status": previous_request.status,
            "last_request_type": previous_request.request_type,
            "last_missing_inputs": _load_missing_inputs(previous_request.missing_inputs),
            "last_final_response": previous_request.final_response,
            "last_resolved_references": _load_json_field(previous_request.resolved_references),
            "last_task_snapshot": _load_task_snapshot(previous_request.task_snapshot),
        }
    session_summary = session_summary_service.load(session_record.session_summary)
    session_context = entity_memory_service.merge_into_session_context(
        session_context=session_context,
        session_summary=session_summary,
    )

    # 자연어 승인/거절: 이전 요청이 pending_approval이면 intent 감지
    if previous_request is not None and previous_request.status == "pending_approval":
        # P0: TTL 만료 확인
        try:
            _check_ttl(previous_request)
        except HTTPException:
            # 만료된 경우 상태 업데이트 후 사용자에게 알림
            previous_request.status = RequestStatus.APPROVAL_EXPIRED.value
            previous_request.final_response = "요청이 만료되었습니다. 다시 요청해주세요."
            db_session.commit()
            _append_user_message(
                db_session,
                session_id=previous_request.session_id,
                request_id=previous_request.id,
                user_id=auth.user_id,
                message_text=payload.message,
            )
            _sync_assistant_message(db_session, previous_request)
            return _build_request_response(previous_request, payload.message)

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
        if intent == ApprovalIntent.UNKNOWN and _expects_exact_name_confirmation(previous_request):
            return _handle_natural_language_approval(
                previous_request=previous_request,
                message_text=payload.message,
                session_id=session_id,
                auth=auth,
                db_session=db_session,
                graph_service=graph_service,
                approval_granted=payload.message.strip(),
            )
        if intent == ApprovalIntent.CORRECTION:
            superseded_request = previous_request
            _supersede_pending_request(superseded_request)
            db_session.flush()
        # UNKNOWN falls through to normal flow

    graph_message_text = payload.message
    rewritten_follow_up = follow_up_interpreter.rewrite(
        message_text=payload.message,
        previous_request_status=previous_request.status if previous_request is not None else None,
        session_context=session_context,
    )
    if rewritten_follow_up is not None:
        graph_message_text = rewritten_follow_up.message_text

    route_decision = conversation_router.decide(
        message_text=graph_message_text,
        session_context=session_context,
    )
    if rewritten_follow_up is None and route_decision.route in {"small_talk", "bridge"}:
        request_id = IdGenerator.generate_sonyflake_id()
        record = repo.create(
            request_id=request_id,
            session_id=session_id,
            user_id=auth.user_id,
            message_text=payload.message,
            effective_message_text=graph_message_text,
            request_type="inquiry",
            requires_approval=False,
        )
        record.status = RequestStatus.COMPLETED.value
        record.final_response = route_decision.response
        if superseded_request is not None:
            _supersede_pending_request(superseded_request, replacement_request_id=record.id)
        db_session.commit()
        db_session.refresh(record)
        event_service = EventService(db_session)
        _append_request_created_event(event_service, record=record)
        _append_context_hydrated_event(
            event_service,
            record=record,
            session_context=session_context,
        )
        _append_structured_event(
            event_service,
            request_id=record.id,
            session_id=record.session_id,
            event_type="response.completed",
            phase="response",
            step="completed",
            message="대화 응답을 생성했습니다.",
            status_value=record.status,
            progress=100,
            payload={"final_response": record.final_response, "task": None},
        )
        _append_user_message(
            db_session,
            session_id=record.session_id,
            request_id=record.id,
            user_id=auth.user_id,
            message_text=payload.message,
        )
        _sync_assistant_message(db_session, record)
        return _build_request_response(record, record.message_text)

    preview = _preview_request(
        graph_service,
        message_text=graph_message_text,
        session_context=session_context,
    )
    if preview is not None and preview.get("request_type") in {"inquiry", "query", "command"}:
        request_id = IdGenerator.generate_sonyflake_id()
        request_type = str(preview.get("request_type") or "")
        record = repo.create(
            request_id=request_id,
            session_id=session_id,
            user_id=auth.user_id,
            message_text=payload.message,
            effective_message_text=str(preview.get("effective_message_text") or payload.message),
            request_type=request_type,
            requires_approval=False,
        )
        record.status = RequestStatus.PROCESSING.value
        if superseded_request is not None:
            _supersede_pending_request(superseded_request, replacement_request_id=record.id)
        db_session.commit()
        db_session.refresh(record)
        _append_user_message(
            db_session,
            session_id=record.session_id,
            request_id=record.id,
            user_id=auth.user_id,
            message_text=payload.message,
        )
        event_service = EventService(db_session)
        _append_request_created_event(event_service, record=record)
        _append_context_hydrated_event(
            event_service,
            record=record,
            session_context=session_context,
        )
        if superseded_request is not None:
            event_service.append_event(
                request_id=superseded_request.id,
                session_id=superseded_request.session_id,
                event_type="approval.superseded",
                payload={
                    "type": "approval.superseded",
                    "request_id": superseded_request.id,
                    "session_id": superseded_request.session_id,
                    "status": superseded_request.status,
                    "superseded_by": record.id,
                    "task": _load_task_snapshot(superseded_request.task_snapshot),
                },
            )

        session_factory = _build_session_factory(db_session)
        threading.Thread(
            target=_process_async_request,
            kwargs={
                "session_factory": session_factory,
                "graph_service": graph_service,
                "request_id": record.id,
                "session_id": session_id,
                "user_id": auth.user_id,
                "user_role": auth.user_role,
                "message_text": graph_message_text,
                "session_context": session_context,
            },
            daemon=True,
        ).start()
        return _build_request_response(record, record.message_text)

    graph_result = _invoke_graph_handle_request(
        graph_service,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=graph_message_text,
        user_role=auth.user_role,
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
    record.task_snapshot = _dump_json_field(graph_result.task_snapshot)
    record.plan_object = _dump_json_field(graph_result.plan_object)
    record.verifier_decision = _dump_json_field(graph_result.verifier_decision)
    record.specialist_result = _dump_json_field(graph_result.specialist_result)
    if superseded_request is not None:
        _supersede_pending_request(superseded_request, replacement_request_id=record.id)
    db_session.commit()
    db_session.refresh(record)
    _sync_session_summary(
        db_session,
        session_id=record.session_id,
        user_id=auth.user_id,
        session_summary=_build_session_summary(
            db_session=db_session,
            session_id=record.session_id,
            user_id=auth.user_id,
            message_text=payload.message,
            graph_result=graph_result,
        ),
    )
    event_service = EventService(db_session)
    _append_request_lifecycle_events(
        event_service,
        record=record,
        graph_result=graph_result,
        session_context=session_context,
        audit_context=_build_graph_audit_context(graph_result, auth.user_id),
    )
    if superseded_request is not None:
        event_service.append_event(
            request_id=superseded_request.id,
            session_id=superseded_request.session_id,
            event_type="approval.superseded",
            payload={
                "type": "approval.superseded",
                "request_id": superseded_request.id,
                "session_id": superseded_request.session_id,
                "status": superseded_request.status,
                "superseded_by": record.id,
                "task": _load_task_snapshot(superseded_request.task_snapshot),
            },
        )

    _append_user_message(
        db_session,
        session_id=record.session_id,
        request_id=record.id,
        user_id=auth.user_id,
        message_text=payload.message,
    )
    _sync_assistant_message(db_session, record)
    return _build_request_response(record, record.message_text)


def _handle_natural_language_approval(
    previous_request: RequestRecord,
    message_text: str,
    session_id: int,
    auth: AuthContext,
    db_session: Session,
    graph_service: GraphService,
    approval_granted: bool | str = True,
) -> RequestResponse:
    """Handle '응', '실행해' etc. as approval for the pending request."""
    # P0: 중복 실행 방지 — 원자적 상태 전이
    transitioned = _atomic_status_transition(
        db_session, previous_request.id,
        from_status=RequestStatus.PENDING_APPROVAL.value,
        to_status=RequestStatus.EXECUTING.value,
    )
    if not transitioned:
        db_session.refresh(previous_request)
        if previous_request.status == RequestStatus.EXECUTING.value:
            return RequestResponse(
                request_id=previous_request.id,
                session_id=previous_request.session_id,
                status=previous_request.status,
                message=message_text,
                assistant_message="이 요청은 현재 처리 중입니다.",
                request_type=previous_request.request_type,
                requires_approval=False,
                final_response="이 요청은 현재 처리 중입니다.",
                created_at=previous_request.created_at,
                updated_at=previous_request.updated_at,
            )
        if previous_request.status in (
            RequestStatus.EXECUTED.value,
            RequestStatus.COMPLETED.value,
        ):
            return RequestResponse(
                request_id=previous_request.id,
                session_id=previous_request.session_id,
                status=previous_request.status,
                message=message_text,
                assistant_message="이 요청은 이미 처리되었습니다.",
                request_type=previous_request.request_type,
                requires_approval=False,
                final_response="이 요청은 이미 처리되었습니다.",
                created_at=previous_request.created_at,
                updated_at=previous_request.updated_at,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is in '{previous_request.status}' state",
        )

    _append_execution_started_event(EventService(db_session), record=previous_request)
    graph_result = graph_service.resume_request(
        request_id=previous_request.id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=previous_request.message_text,
        approval_granted=approval_granted,
        user_role=auth.user_role,
    )
    previous_request.status = graph_result.status
    previous_request.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    previous_request.final_response = graph_result.final_response
    previous_request.requires_approval = graph_result.requires_approval
    previous_request.task_snapshot = _dump_json_field(graph_result.task_snapshot)
    previous_request.plan_object = _dump_json_field(graph_result.plan_object)
    previous_request.verifier_decision = _dump_json_field(graph_result.verifier_decision)
    previous_request.specialist_result = _dump_json_field(graph_result.specialist_result)
    db_session.commit()
    db_session.refresh(previous_request)
    _sync_session_summary(
        db_session,
        session_id=previous_request.session_id,
        user_id=auth.user_id,
        session_summary=_build_session_summary(
            db_session=db_session,
            session_id=previous_request.session_id,
            user_id=auth.user_id,
            message_text=previous_request.message_text,
            graph_result=graph_result,
        ),
    )
    _append_execution_terminal_event(
        EventService(db_session),
        record=previous_request,
        graph_result=graph_result,
        user_id=auth.user_id,
    )
    _append_user_message(
        db_session,
        session_id=previous_request.session_id,
        request_id=previous_request.id,
        user_id=auth.user_id,
        message_text=message_text,
    )
    _sync_assistant_message(db_session, previous_request)
    return _build_request_response(previous_request, message_text)


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
    )
    previous_request.status = graph_result.status
    previous_request.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    previous_request.final_response = graph_result.final_response
    previous_request.requires_approval = graph_result.requires_approval
    previous_request.task_snapshot = _dump_json_field(graph_result.task_snapshot)
    previous_request.plan_object = _dump_json_field(graph_result.plan_object)
    previous_request.verifier_decision = _dump_json_field(graph_result.verifier_decision)
    previous_request.specialist_result = _dump_json_field(graph_result.specialist_result)
    db_session.commit()
    db_session.refresh(previous_request)
    _sync_session_summary(
        db_session,
        session_id=previous_request.session_id,
        user_id=auth.user_id,
        session_summary=_build_session_summary(
            db_session=db_session,
            session_id=previous_request.session_id,
            user_id=auth.user_id,
            message_text=previous_request.message_text,
            graph_result=graph_result,
        ),
    )
    EventService(db_session).append_audit_event(
        request_id=previous_request.id,
        session_id=previous_request.session_id,
        event_type="approval.rejected",
        payload={
            "type": "approval.rejected",
            "request_id": previous_request.id,
            "session_id": previous_request.session_id,
            "status": previous_request.status,
            "task": _load_task_snapshot(previous_request.task_snapshot),
        },
        audit_context=_build_graph_audit_context(graph_result, auth.user_id),
    )
    _append_user_message(
        db_session,
        session_id=previous_request.session_id,
        request_id=previous_request.id,
        user_id=auth.user_id,
        message_text=message_text,
    )
    _sync_assistant_message(db_session, previous_request)
    return _build_request_response(previous_request, message_text)


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
        task=_load_task_snapshot(record.task_snapshot),
        plan=_load_plan_object(record.plan_object),
        verifier=_load_verifier_decision(record.verifier_decision),
        specialist=_load_specialist_result(record.specialist_result),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("/{request_id}/approve", response_model=ApproveRequestResponse)
def approve_request(
    session_id: int,
    request_id: int,
    payload: ApproveRequestRequest | None = None,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
    graph_service: GraphService = Depends(get_graph_service),
) -> ApproveRequestResponse:
    session_record = SessionRepository(db_session).get_for_user(session_id=session_id, user_id=auth.user_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    record = _load_request_or_404(db_session, request_id=request_id, user_id=auth.user_id)

    # P0: TTL 만료 확인
    _check_ttl(record)

    # P0: 중복 실행 방지 — 원자적 상태 전이
    transitioned = _atomic_status_transition(
        db_session, request_id,
        from_status=RequestStatus.PENDING_APPROVAL.value,
        to_status=RequestStatus.EXECUTING.value,
    )
    if not transitioned:
        db_session.refresh(record)
        if record.status == RequestStatus.EXECUTING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이 요청은 현재 처리 중입니다.",
            )
        if record.status in (RequestStatus.EXECUTED.value, RequestStatus.COMPLETED.value):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이 요청은 이미 처리되었습니다.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request is not pending approval",
        )

    _append_execution_started_event(EventService(db_session), record=record)
    graph_result = graph_service.resume_request(
        request_id=request_id,
        session_id=session_id,
        user_id=auth.user_id,
        message_text=record.message_text,
        approval_granted=(payload.confirmation_text.strip() if payload and payload.confirmation_text else True),
        user_role=auth.user_role,
    )
    record.status = graph_result.status
    record.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    record.final_response = graph_result.final_response
    record.requires_approval = graph_result.requires_approval
    record.task_snapshot = _dump_json_field(graph_result.task_snapshot)
    record.plan_object = _dump_json_field(graph_result.plan_object)
    record.verifier_decision = _dump_json_field(graph_result.verifier_decision)
    record.specialist_result = _dump_json_field(graph_result.specialist_result)
    db_session.commit()
    db_session.refresh(record)
    _sync_session_summary(
        db_session,
        session_id=record.session_id,
        user_id=auth.user_id,
        session_summary=_build_session_summary(
            db_session=db_session,
            session_id=record.session_id,
            user_id=auth.user_id,
            message_text=record.message_text,
            graph_result=graph_result,
        ),
    )
    _append_execution_terminal_event(
        EventService(db_session),
        record=record,
        graph_result=graph_result,
        user_id=auth.user_id,
    )
    _sync_assistant_message(db_session, record)
    return ApproveRequestResponse(
        request_id=record.id,
        status=record.status,
        assistant_message=record.final_response,
        task=_load_task_snapshot(record.task_snapshot),
        plan=_load_plan_object(record.plan_object),
        verifier=_load_verifier_decision(record.verifier_decision),
        specialist=_load_specialist_result(record.specialist_result),
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
    )
    record.status = graph_result.status
    record.missing_inputs = _dump_missing_inputs(graph_result.missing_inputs)
    record.final_response = graph_result.final_response
    record.requires_approval = graph_result.requires_approval
    record.task_snapshot = _dump_json_field(graph_result.task_snapshot)
    record.plan_object = _dump_json_field(graph_result.plan_object)
    record.verifier_decision = _dump_json_field(graph_result.verifier_decision)
    record.specialist_result = _dump_json_field(graph_result.specialist_result)
    db_session.commit()
    db_session.refresh(record)
    _sync_session_summary(
        db_session,
        session_id=record.session_id,
        user_id=auth.user_id,
        session_summary=_build_session_summary(
            db_session=db_session,
            session_id=record.session_id,
            user_id=auth.user_id,
            message_text=record.message_text,
            graph_result=graph_result,
        ),
    )
    EventService(db_session).append_audit_event(
        request_id=record.id,
        session_id=record.session_id,
        event_type="approval.rejected",
        payload={
            "type": "approval.rejected",
            "request_id": record.id,
            "session_id": record.session_id,
            "status": record.status,
            "task": _load_task_snapshot(record.task_snapshot),
        },
        audit_context=_build_graph_audit_context(graph_result, auth.user_id),
    )
    _sync_assistant_message(db_session, record)
    return RejectRequestResponse(
        request_id=record.id,
        status=record.status,
        assistant_message=record.final_response,
        task=_load_task_snapshot(record.task_snapshot),
        plan=_load_plan_object(record.plan_object),
        verifier=_load_verifier_decision(record.verifier_decision),
        specialist=_load_specialist_result(record.specialist_result),
    )
