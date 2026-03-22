from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from chatops.api.dependencies import get_db_session, get_graph_service
from chatops.app import create_app
from chatops.db.repositories import (
    RequestEventRepository,
    RequestRepository,
    SessionRepository,
)
from chatops.domain.enums import RequestStatus
from chatops.graph.service import GraphResult
from chatops.schemas.events import RequestEventResponse
from chatops.schemas.requests import (
    ApproveRequestResponse,
    CreateRequestRequest,
    RejectRequestResponse,
    RequestResponse,
)
from chatops.services.auth import build_auth_context


@dataclass
class StubGraphService:
    status: str = "pending_approval"
    requires_approval: bool = True

    def handle_request(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
    ) -> GraphResult:
        return GraphResult(
            request_id=2001,
            session_id=session_id,
            user_id=user_id,
            status=self.status,
            request_type="command",
            requires_approval=self.requires_approval,
            intent="execute_command",
            final_response=None,
            selected_operation_ids=["project.create"],
        )

    def resume_request(
        self,
        request_id: int,
        session_id: int,
        user_id: str,
        message_text: str,
        approval_granted: bool = True,
        user_role: str | None = None,
        org_id: str | None = None,
    ) -> GraphResult:
        return GraphResult(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            status="completed" if approval_granted else "rejected",
            request_type="command",
            requires_approval=False,
            intent="execute_command",
            final_response="명령 실행 완료" if approval_granted else "명령 실행 거절",
            selected_operation_ids=["project.create"],
        )


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService()

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_request_repository_updates_status(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    repo = RequestRepository(db_session)

    request = repo.create(
        session_id=session.id,
        user_id="user-1",
        message_text="프로젝트 생성해줘",
    )
    updated = repo.update_status(request.id, RequestStatus.PENDING_APPROVAL.value)

    assert updated is not None
    assert isinstance(request.id, int)
    assert request.id > 0
    assert updated.status == RequestStatus.PENDING_APPROVAL.value


def test_request_event_repository_lists_after_sequence(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="상태 알려줘",
    )
    repo = RequestEventRepository(db_session)

    repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=1,
        event_type="request.created",
        payload="{}",
    )
    second = repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=2,
        event_type="response.completed",
        payload='{"status":"completed"}',
    )

    events = repo.list_after_sequence(request.id, 1)

    assert isinstance(second.id, int)
    assert [event.id for event in events] == [second.id]


def test_request_event_repository_rejects_duplicate_sequence(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="상태 알려줘",
    )
    repo = RequestEventRepository(db_session)

    repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=1,
        event_type="request.created",
        payload="{}",
    )

    with pytest.raises(IntegrityError):
        repo.append(
            request_id=request.id,
            session_id=session.id,
            sequence=1,
            event_type="response.completed",
            payload='{"status":"completed"}',
        )


def test_request_schemas_and_auth_context_match_contract() -> None:
    auth = build_auth_context(
        user_id="user-1",
        request_id="req-header-1",
        user_role="admin",
        org_id="org-1",
    )
    create_payload = CreateRequestRequest(message="프로젝트 생성해줘")
    request_response = RequestResponse(
        request_id=2001,
        session_id=1001,
        status="processing",
        message=create_payload.message,
    )
    approved = ApproveRequestResponse(request_id=2001, status="approved")
    rejected = RejectRequestResponse(request_id=2001, status="rejected")
    event = RequestEventResponse(
        sequence=2,
        type="response.completed",
        data={"status": "completed"},
        timestamp=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )

    assert auth.user_id == "user-1"
    assert auth.request_id == "req-header-1"
    assert request_response.model_dump()["message"] == "프로젝트 생성해줘"
    assert approved.status == "approved"
    assert rejected.status == "rejected"
    assert event.model_dump()["sequence"] == 2


def test_create_request_returns_processing_status(client: TestClient) -> None:
    session = client.post(
        "/api/v1/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()

    response = client.post(
        f"/api/v1/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    )

    assert response.status_code == 202
    assert isinstance(response.json()["request_id"], int)
    assert response.json()["status"] in {"processing", "pending_approval"}


def test_approve_request_resumes_pending_command(client: TestClient) -> None:
    session = client.post(
        "/api/v1/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()
    request = client.post(
        f"/api/v1/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    ).json()

    response = client.post(
        f"/api/v1/sessions/{session['session_id']}/requests/{request['request_id']}/approve",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_reject_request_emits_rejected_event(client: TestClient) -> None:
    session = client.post(
        "/api/v1/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()
    request = client.post(
        f"/api/v1/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    ).json()

    response = client.post(
        f"/api/v1/sessions/{session['session_id']}/requests/{request['request_id']}/reject",
        headers={"X-User-Id": "user-1"},
    )
    stream_response = client.get(
        f"/api/v1/sessions/{session['session_id']}/requests/{request['request_id']}/stream",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "event: approval.rejected" in stream_response.text
