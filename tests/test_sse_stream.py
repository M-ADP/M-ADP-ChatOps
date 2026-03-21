from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from chatops.api.dependencies import get_db_session, get_graph_service
from chatops.app import create_app
from chatops.db.repositories import RequestRepository, SessionRepository
from chatops.graph.service import GraphResult
from chatops.services.events import EventService


class StubGraphService:
    def handle_request(
        self,
        session_id: str,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
    ) -> GraphResult:
        return GraphResult(
            request_id="graph-request-id",
            session_id=session_id,
            user_id=user_id,
            status="pending_approval",
            request_type="command",
            requires_approval=True,
            intent="execute_command",
            final_response="실행 계획입니다.",
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


def test_event_service_assigns_monotonic_sequence(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="프로젝트 생성해줘",
    )
    service = EventService(db_session)

    first = service.append_event(
        request_id=request.id,
        session_id=session.id,
        event_type="request.created",
        payload={"type": "request.created"},
    )
    second = service.append_event(
        request_id=request.id,
        session_id=session.id,
        event_type="approval.required",
        payload={"type": "approval.required"},
    )

    assert first.sequence == 1
    assert second.sequence == 2


def test_request_stream_replays_events_after_sequence(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="프로젝트 생성해줘",
    )
    service = EventService(db_session)
    service.append_event(
        request_id=request.id,
        session_id=session.id,
        event_type="request.created",
        payload={"type": "request.created", "request_id": request.id},
    )
    service.append_event(
        request_id=request.id,
        session_id=session.id,
        event_type="response.delta",
        payload={"type": "response.delta", "request_id": request.id, "text": "계획"},
    )

    response = client.get(
        f"/api/v1/sessions/{session.id}/requests/{request.id}/stream",
        headers={"X-User-Id": "user-1", "Last-Event-ID": "1"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "id: 2" in body
    assert "event: response.delta" in body
    assert json.dumps({"type": "response.delta", "request_id": request.id, "text": "계획"}, ensure_ascii=False) in body


def test_create_request_emits_initial_events(client: TestClient) -> None:
    session = client.post(
        "/api/v1/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()

    create_response = client.post(
        f"/api/v1/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    )
    request_id = create_response.json()["request_id"]

    stream_response = client.get(
        f"/api/v1/sessions/{session['session_id']}/requests/{request_id}/stream",
        headers={"X-User-Id": "user-1"},
    )

    body = stream_response.text
    assert "event: request.created" in body
    assert "event: approval.required" in body
