from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from chatops.api.dependencies import get_db_session, get_graph_service
from chatops.app import create_app
from chatops.db.repositories import RequestRepository, SessionRepository
from chatops.graph.service import GraphResult
from chatops.services.events import EventService


class StubGraphService:
    def handle_request(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
        session_context: dict[str, object] | None = None,
    ) -> GraphResult:
        del session_context
        return GraphResult(
            request_id=2001,
            session_id=session_id,
            user_id=user_id,
            status="pending_approval",
            request_type="command",
            requires_approval=True,
            intent="execute_command",
            final_response="실행 계획입니다.",
            selected_operation_ids=["project.create"],
            missing_inputs=None,
        )


class StreamingStubGraphService:
    def preview_request(
        self,
        message_text: str,
        session_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del session_context
        return {
            "request_type": "inquiry",
            "effective_message_text": message_text,
            "intent": "answer_inquiry",
        }

    def handle_request(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
        session_context: dict[str, object] | None = None,
        request_id: int | None = None,
        response_stream_handler=None,
    ) -> GraphResult:
        del user_role, org_id, session_context
        time.sleep(0.2)
        if response_stream_handler is not None:
            response_stream_handler("문의 ")
            time.sleep(0.05)
            response_stream_handler("응답")
        return GraphResult(
            request_id=request_id or 7001,
            session_id=session_id,
            user_id=user_id,
            status="completed",
            request_type="inquiry",
            requires_approval=False,
            intent="answer_inquiry",
            final_response=f"{message_text} 문의 응답",
            selected_operation_ids=[],
            missing_inputs=None,
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
        f"/chatops/sessions/{session.id}/requests/{request.id}/stream",
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
        "/chatops/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()

    create_response = client.post(
        f"/chatops/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    )
    request_id = create_response.json()["request_id"]

    stream_response = client.get(
        f"/chatops/sessions/{session['session_id']}/requests/{request_id}/stream",
        headers={"X-User-Id": "user-1"},
    )

    body = stream_response.text
    assert "event: request.created" in body
    assert "event: context.hydrated" in body
    assert "event: parsing.completed" in body
    assert "event: approval.required" in body


def test_request_stream_follow_waits_for_future_events(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="진행 상황 보여줘",
        request_id=6101,
    )
    request.status = "executing"
    db_session.commit()

    background_session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        future=True,
    )

    def append_event_later() -> None:
        time.sleep(0.2)
        worker_session = background_session_factory()
        try:
            request_record = RequestRepository(worker_session).get_for_user(request_id=request.id, user_id="user-1")
            assert request_record is not None
            request_record.status = "completed"
            EventService(worker_session).append_event(
                request_id=request.id,
                session_id=session.id,
                event_type="response.delta",
                payload={"type": "response.delta", "request_id": request.id, "text": "50%"},
            )
        finally:
            worker_session.close()

    worker = threading.Thread(target=append_event_later)
    worker.start()
    try:
        with client.stream(
            "GET",
            f"/chatops/sessions/{session.id}/requests/{request.id}/stream",
            headers={"X-User-Id": "user-1"},
            params={"follow": "true"},
        ) as response:
            body = response.read().decode()
    finally:
        worker.join(timeout=2)

    assert response.status_code == 200
    assert "event: response.delta" in body
    assert '"text": "50%"' in body


def test_create_request_returns_immediately_and_streams_ai_deltas(db_session) -> None:
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StreamingStubGraphService()

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        started_at = time.monotonic()
        create_response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "배포 방법 알려줘"},
        )
        elapsed = time.monotonic() - started_at
        request_id = create_response.json()["request_id"]

        with client.stream(
            "GET",
            f"/chatops/sessions/{session['session_id']}/requests/{request_id}/stream",
            headers={"X-User-Id": "user-1"},
            params={"follow": "true"},
        ) as response:
            body = response.read().decode()

    app.dependency_overrides.clear()

    assert create_response.status_code == 202
    assert elapsed < 0.15
    assert "event: request.created" in body
    assert "event: response.delta" in body
    assert '"text": "문의 "' in body
    assert '"text": "응답"' in body
    assert "event: response.completed" in body
