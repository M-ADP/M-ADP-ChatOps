from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from chatops.api.dependencies import get_db_session, get_graph_service
from chatops.app import create_app
from chatops.db.repositories import RequestRepository, SessionRepository
from chatops.graph.service import GraphResult
from chatops.schemas.sessions import CreateSessionRequest, SessionResponse
from chatops.services.auth import build_auth_context


@dataclass
class StubGraphService:
    status: str = "pending_approval"
    requires_approval: bool = True
    effective_message_text: str | None = None
    next_request_id: int = 4001
    task_snapshot: dict[str, object] | None = None
    final_response: str | None = "계획을 검토하고 승인하면 바로 실행합니다."

    def handle_request(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        session_context: dict[str, object] | None = None,
    ) -> GraphResult:
        del user_role, session_context
        request_id = self.next_request_id
        self.next_request_id += 1
        return GraphResult(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            status=self.status,
            request_type="command",
            requires_approval=self.requires_approval,
            intent="execute_command",
            final_response=self.final_response,
            selected_operation_ids=["application.create_apps"],
            missing_inputs=None,
            effective_message_text=self.effective_message_text,
            task_snapshot=self.task_snapshot,
        )


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_session_persists_owner(db_session) -> None:
    repo = SessionRepository(db_session)

    session = repo.create(user_id="user-1", title=None)

    assert isinstance(session.id, int)
    assert session.id > 0
    assert session.user_id == "user-1"
    assert session.status == "active"


def test_build_auth_context_requires_x_user_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        build_auth_context(user_id=None)

    assert exc_info.value.status_code == 401


def test_session_schemas_use_api_contract_fields() -> None:
    payload = CreateSessionRequest(title="운영 세션")
    response = SessionResponse(
        session_id=1001,
        user_id="user-1",
        title=payload.title,
        status="active",
    )

    assert payload.model_dump() == {"title": "운영 세션"}
    assert response.model_dump()["session_id"] == 1001


def test_create_session_returns_owned_session(client: TestClient) -> None:
    response = client.post(
        "/sessions",
        headers={"X-User-Id": "user-1"},
        json={"title": "운영 세션"},
    )

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["session_id"], int)
    assert body["user_id"] == "user-1"
    assert body["status"] == "active"


def test_sessions_preflight_allows_any_origin(client: TestClient) -> None:
    response = client.options(
        "/sessions",
        headers={
            "Origin": "https://frontend.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "POST" in response.headers["access-control-allow-methods"]


def _store_request(
    db_session,
    *,
    session_id: int,
    user_id: str,
    message_text: str,
    final_response: str | None,
    status: str = "completed",
    task_snapshot: dict[str, object] | None = None,
    plan_object: dict[str, object] | None = None,
    verifier_decision: dict[str, object] | None = None,
    specialist_result: dict[str, object] | None = None,
) -> None:
    record = RequestRepository(db_session).create(
        session_id=session_id,
        user_id=user_id,
        message_text=message_text,
        request_type="command",
        requires_approval=status == "pending_approval",
    )
    record.status = status
    record.final_response = final_response
    record.task_snapshot = json.dumps(task_snapshot, ensure_ascii=False) if task_snapshot else None
    record.plan_object = json.dumps(plan_object, ensure_ascii=False) if plan_object else None
    record.verifier_decision = json.dumps(verifier_decision, ensure_ascii=False) if verifier_decision else None
    record.specialist_result = json.dumps(specialist_result, ensure_ascii=False) if specialist_result else None
    db_session.commit()


def test_list_sessions_returns_last_message_preview_and_cursor(client: TestClient, db_session) -> None:
    session_repo = SessionRepository(db_session)
    first = session_repo.create(user_id="user-1", title="첫 번째 세션")
    second = session_repo.create(user_id="user-1", title="두 번째 세션")
    third = session_repo.create(user_id="user-1", title="세 번째 세션")
    _store_request(
        db_session,
        session_id=first.id,
        user_id="user-1",
        message_text="첫 번째 요청",
        final_response="첫 번째 응답",
    )
    _store_request(
        db_session,
        session_id=second.id,
        user_id="user-1",
        message_text="두 번째 요청",
        final_response="두 번째 응답",
    )
    _store_request(
        db_session,
        session_id=third.id,
        user_id="user-1",
        message_text="세 번째 요청",
        final_response="세 번째 응답",
    )

    response = client.get(
        "/sessions?limit=2",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["sessions"]) == 2
    assert body["sessions"][0]["title"] == "세 번째 세션"
    assert body["sessions"][0]["last_message_preview"] == "세 번째 응답"
    assert body["sessions"][1]["title"] == "두 번째 세션"
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str)


def test_get_session_returns_recent_messages_with_cursor(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="대화 복원")
    _store_request(
        db_session,
        session_id=session.id,
        user_id="user-1",
        message_text="demo 프로젝트에 api 앱 만들어줘",
        final_response="계획을 검토하고 승인하면 바로 실행합니다.",
        status="pending_approval",
        task_snapshot={
            "title": "애플리케이션 생성",
            "status": "pending_approval",
            "approval_state": "awaiting_approval",
            "next_actions": ["approve", "edit", "cancel"],
        },
    )
    _store_request(
        db_session,
        session_id=session.id,
        user_id="user-1",
        message_text="승인",
        final_response="api 앱 생성을 완료했습니다.",
        status="completed",
        task_snapshot={
            "title": "애플리케이션 생성",
            "status": "completed",
            "approval_state": "completed",
            "next_actions": ["view_result"],
        },
    )

    response = client.get(
        f"/sessions/{session.id}?limit=2",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["session_id"] == session.id
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["text"] == "승인"
    assert body["messages"][1]["type"] == "task"
    assert body["messages"][1]["task"]["approval_state"] == "completed"
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str)


def test_get_session_messages_paginates_older_history(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="페이지네이션")
    _store_request(
        db_session,
        session_id=session.id,
        user_id="user-1",
        message_text="첫 요청",
        final_response="첫 응답",
    )
    _store_request(
        db_session,
        session_id=session.id,
        user_id="user-1",
        message_text="둘 요청",
        final_response="둘 응답",
    )

    latest = client.get(
        f"/sessions/{session.id}?limit=2",
        headers={"X-User-Id": "user-1"},
    )
    older = client.get(
        f"/sessions/{session.id}/messages?before={latest.json()['next_cursor']}&limit=2",
        headers={"X-User-Id": "user-1"},
    )

    assert latest.status_code == 200
    assert older.status_code == 200
    assert [message["text"] for message in latest.json()["messages"]] == ["둘 요청", "둘 응답"]
    assert [message["text"] for message in older.json()["messages"]] == ["첫 요청", "첫 응답"]
    assert older.json()["has_more"] is False
    assert older.json()["next_cursor"] is None


def test_session_history_returns_requests_in_chronological_order(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="운영")
    repo = RequestRepository(db_session)
    first = repo.create(session_id=session.id, user_id="user-1", message_text="첫 요청", request_id=5301, request_type="query")
    first.status = "completed"
    second = repo.create(session_id=session.id, user_id="user-1", message_text="둘째 요청", request_id=5302, request_type="command")
    second.status = "failed"
    db_session.commit()

    response = client.get(
        f"/sessions/{session.id}/history",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["request_id"] for item in body["items"]] == [5301, 5302]


def test_post_session_message_returns_user_and_assistant_messages(db_session) -> None:
    app = create_app()
    task_snapshot = {
        "title": "애플리케이션 생성",
        "status": "pending_approval",
        "approval_state": "awaiting_approval",
        "next_actions": ["approve", "edit", "cancel"],
    }

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService(task_snapshot=task_snapshot)

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={"title": "메시지 전송"},
        ).json()

        response = client.post(
            f"/sessions/{session['session_id']}/messages",
            headers={"X-User-Id": "user-1", "X-User-Role": "admin"},
            json={"message": "demo 프로젝트에 api 앱 만들어줘"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["text"] == "demo 프로젝트에 api 앱 만들어줘"
    assert body["messages"][1]["type"] == "task"
    assert body["messages"][1]["task"]["title"] == "애플리케이션 생성"


def test_get_session_projects_runtime_metadata_into_assistant_message(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="runtime projection")
    _store_request(
        db_session,
        session_id=session.id,
        user_id="user-1",
        message_text="demo 프로젝트에 api 앱 만들어줘",
        final_response="계획을 검토하고 승인하면 바로 실행합니다.",
        status="pending_approval",
        task_snapshot={
            "title": "애플리케이션 생성",
            "status": "pending_approval",
            "approval_state": "awaiting_approval",
            "next_actions": ["approve", "edit", "cancel"],
        },
        plan_object={
            "goal": "demo 프로젝트에 api 앱 생성",
            "specialist": "application",
            "entities": {"project_name": "demo", "application_name": "api"},
            "constraints": {"approval_required": True},
            "candidate_steps": [
                {
                    "step_id": "create-app",
                    "title": "앱 생성",
                    "status": "planned",
                    "operation_id": "application.create_apps",
                }
            ],
            "risk_level": "medium",
            "required_clarifications": ["cpu", "memory", "disk"],
        },
        verifier_decision={
            "decision": "clarify",
            "summary": "리소스 값이 더 필요합니다.",
            "missing_inputs": ["cpu", "memory", "disk"],
            "follow_up_action": "fill_inputs",
        },
        specialist_result={
            "specialist": "application",
            "operation_id": "application.create_apps",
            "summary": "애플리케이션 specialist를 선택했습니다.",
            "resolved_inputs": {"name": "api"},
            "missing_inputs": ["cpu", "memory", "disk"],
        },
    )

    response = client.get(
        f"/sessions/{session.id}?limit=10",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assistant_message = response.json()["messages"][1]
    assert assistant_message["plan"]["specialist"] == "application"
    assert assistant_message["verifier"]["decision"] == "clarify"
    assert assistant_message["specialist"]["operation_id"] == "application.create_apps"
