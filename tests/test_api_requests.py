from __future__ import annotations

import json
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
from chatops.schemas.tasks import TaskSnapshot
from chatops.services.auth import build_auth_context


@dataclass
class StubGraphService:
    status: str = "pending_approval"
    requires_approval: bool = True
    missing_inputs: list[str] | None = None
    last_session_context: dict[str, object] | None = None
    effective_message_text: str | None = None
    next_request_id: int = 2001
    task_snapshot: dict[str, object] | None = None
    resumed_task_snapshot: dict[str, object] | None = None
    plan_object: dict[str, object] | None = None
    verifier_decision: dict[str, object] | None = None
    specialist_result: dict[str, object] | None = None
    session_summary: dict[str, object] | None = None

    def handle_request(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
        session_context: dict[str, object] | None = None,
    ) -> GraphResult:
        self.last_session_context = session_context
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
            final_response=None,
            selected_operation_ids=["project.create"],
            missing_inputs=self.missing_inputs,
            effective_message_text=self.effective_message_text,
            task_snapshot=self.task_snapshot,
            plan_object=self.plan_object,
            verifier_decision=self.verifier_decision,
            specialist_result=self.specialist_result,
            session_summary=self.session_summary,
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
            missing_inputs=None,
            effective_message_text=self.effective_message_text,
            task_snapshot=self.resumed_task_snapshot or self.task_snapshot,
            plan_object=self.plan_object,
            verifier_decision=self.verifier_decision,
            specialist_result=self.specialist_result,
            session_summary=self.session_summary,
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
        user_role="admin",
    )
    create_payload = CreateRequestRequest(message="프로젝트 생성해줘")
    request_response = RequestResponse(
        request_id=2001,
        session_id=1001,
        status="processing",
        message=create_payload.message,
        assistant_message="처리 중입니다.",
        task=TaskSnapshot(
            title="프로젝트 생성",
            status="processing",
            request_type="command",
            approval_state="not_ready",
            next_actions=["fill_inputs"],
        ),
    )
    approved = ApproveRequestResponse(
        request_id=2001,
        status="approved",
        task=TaskSnapshot(
            title="프로젝트 생성",
            status="completed",
            request_type="command",
            approval_state="completed",
            next_actions=["view_result"],
        ),
    )
    rejected = RejectRequestResponse(
        request_id=2001,
        status="rejected",
        task=TaskSnapshot(
            title="프로젝트 생성",
            status="rejected",
            request_type="command",
            approval_state="cancelled",
            next_actions=["retry"],
        ),
    )
    event = RequestEventResponse(
        sequence=2,
        type="response.completed",
        data={"status": "completed"},
        timestamp=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )

    assert auth.user_id == "user-1"
    assert auth.model_dump() == {"user_id": "user-1", "user_role": "admin"}
    assert request_response.model_dump()["message"] == "프로젝트 생성해줘"
    assert request_response.model_dump()["assistant_message"] == "처리 중입니다."
    assert request_response.model_dump()["task"]["title"] == "프로젝트 생성"
    assert approved.status == "approved"
    assert approved.model_dump()["task"]["approval_state"] == "completed"
    assert rejected.status == "rejected"
    assert rejected.model_dump()["task"]["approval_state"] == "cancelled"
    assert event.model_dump()["sequence"] == 2


def test_openapi_does_not_expose_request_or_org_headers(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    for path_item in payload["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            names = {
                parameter.get("name")
                for parameter in operation.get("parameters", [])
                if isinstance(parameter, dict)
            }
            assert "X-Request-Id" not in names
            assert "X-Org-Id" not in names


def test_openapi_exposes_component_examples_for_apidog_import(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]

    expected_examples = {
        "CreateSessionRequest": {"title": "프로젝트 생성 상담"},
        "CreateRequestRequest": {"message": "demo 프로젝트에 api 앱 만들어줘"},
        "ApproveRequestRequest": {"confirmation_text": "승인"},
        "SessionResponse": {"session_id": 1001, "user_id": "user-1", "status": "active"},
        "RequestResponse": {"request_id": 2001, "status": "pending_approval", "task": {"title": "애플리케이션 생성"}},
        "ApproveRequestResponse": {"request_id": 2001, "status": "completed", "task": {"approval_state": "completed"}},
        "RejectRequestResponse": {"request_id": 2001, "status": "rejected", "task": {"approval_state": "cancelled"}},
        "TaskSnapshot": {"title": "애플리케이션 생성", "status": "pending_approval", "approval_state": "awaiting_approval"},
    }

    for schema_name, expected in expected_examples.items():
        schema = schemas[schema_name]
        assert "example" in schema
        for key, value in expected.items():
            if isinstance(value, dict):
                assert isinstance(schema["example"][key], dict)
                for nested_key, nested_value in value.items():
                    assert schema["example"][key][nested_key] == nested_value
            else:
                assert schema["example"][key] == value


def test_create_request_returns_processing_status(client: TestClient) -> None:
    session = client.post(
        "/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()

    response = client.post(
        f"/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    )

    assert response.status_code == 202
    assert isinstance(response.json()["request_id"], int)
    assert response.json()["status"] in {"processing", "pending_approval"}


def test_request_responses_include_task_snapshot(db_session) -> None:
    app = create_app()
    expected_task = {
        "kind": "operation",
        "title": "프로젝트 생성",
        "status": "pending_approval",
        "request_type": "command",
        "approval_state": "awaiting_approval",
        "operation_id": "project.create",
        "next_actions": ["approve", "edit", "cancel"],
    }

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService(task_snapshot=expected_task)

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        created = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘"},
        )
        request_id = created.json()["request_id"]
        fetched = client.get(
            f"/sessions/{session['session_id']}/requests/{request_id}",
            headers={"X-User-Id": "user-1"},
        )

    app.dependency_overrides.clear()

    assert created.status_code == 202
    assert created.json()["task"] is not None
    for key, value in expected_task.items():
        assert created.json()["task"][key] == value
    assert fetched.status_code == 200
    assert fetched.json()["task"] is not None
    for key, value in expected_task.items():
        assert fetched.json()["task"][key] == value


def test_create_request_persists_runtime_metadata(db_session) -> None:
    app = create_app()
    expected_task = {
        "kind": "operation",
        "title": "애플리케이션 생성",
        "status": "pending_approval",
        "request_type": "command",
        "approval_state": "awaiting_approval",
        "operation_id": "application.create_apps",
        "next_actions": ["approve", "edit", "cancel"],
    }
    expected_plan = {
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
    }
    expected_verifier = {
        "decision": "clarify",
        "summary": "리소스 값이 더 필요합니다.",
        "missing_inputs": ["cpu", "memory", "disk"],
        "follow_up_action": "fill_inputs",
    }
    expected_specialist = {
        "specialist": "application",
        "operation_id": "application.create_apps",
        "summary": "애플리케이션 specialist를 선택했습니다.",
        "resolved_inputs": {"name": "api"},
        "missing_inputs": ["cpu", "memory", "disk"],
    }
    expected_summary = {
        "active_goal": "demo 프로젝트 운영",
        "recent_entities": {"project_name": "demo"},
        "last_completed_task": "앱 상태 조회",
        "last_verifier_decision": "clarify",
        "updated_at": "2026-04-03T00:00:00Z",
    }

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService(
            task_snapshot=expected_task,
            plan_object=expected_plan,
            verifier_decision=expected_verifier,
            specialist_result=expected_specialist,
            session_summary=expected_summary,
        )

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={"title": "runtime"},
        ).json()

        created = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "demo 프로젝트에 api 앱 만들어줘"},
        )

    app.dependency_overrides.clear()

    record = RequestRepository(db_session).get_for_user(created.json()["request_id"], "user-1")
    session_record = SessionRepository(db_session).get_for_user(session["session_id"], "user-1")

    assert created.status_code == 202
    assert created.json()["plan"]["specialist"] == "application"
    assert created.json()["verifier"]["decision"] == "clarify"
    assert created.json()["specialist"]["operation_id"] == "application.create_apps"
    assert record is not None
    assert json.loads(record.plan_object)["specialist"] == "application"
    assert json.loads(record.verifier_decision)["decision"] == "clarify"
    assert json.loads(record.specialist_result)["operation_id"] == "application.create_apps"
    assert session_record is not None
    assert json.loads(session_record.session_summary)["active_goal"] == "demo 프로젝트 운영"


def test_create_request_returns_missing_inputs_when_command_needs_more_values(db_session) -> None:
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService(
            status="input_required",
            requires_approval=False,
            missing_inputs=["name", "project_name"],
        )

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        response = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 수정해줘"},
        )

        request_id = response.json()["request_id"]
        detail = client.get(
            f"/sessions/{session['session_id']}/requests/{request_id}",
            headers={"X-User-Id": "user-1"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["status"] == "input_required"
    assert response.json()["missing_inputs"] == ["name", "project_name"]
    assert response.json()["assistant_message"] is None
    assert detail.status_code == 200
    assert detail.json()["missing_inputs"] == ["name", "project_name"]
    assert detail.json()["assistant_message"] is None


def test_create_request_passes_previous_session_message_as_context(db_session) -> None:
    app = create_app()
    stub_graph_service = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub_graph_service

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        repo = RequestRepository(db_session)
        repo.create(
            session_id=session["session_id"],
            user_id="user-1",
            message_text="프로젝트 456 지워줘",
            request_id=3001,
            request_type="command",
            requires_approval=True,
        )

        response = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "그거 이름은 chatops-renamed로 바꿔줘"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert stub_graph_service.last_session_context == {
        "last_message_text": "프로젝트 456 지워줘",
        "last_request_status": "created",
        "last_request_type": "command",
        "last_missing_inputs": None,
        "last_final_response": None,
        "last_effective_message_text": None,
        "last_resolved_references": None,
    }


def test_create_request_passes_input_required_context_for_follow_up(db_session) -> None:
    app = create_app()
    stub_graph_service = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub_graph_service

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        repo = RequestRepository(db_session)
        request = repo.create(
            session_id=session["session_id"],
            user_id="user-1",
            message_text="프로젝트 하나 만들어줘",
            request_id=3002,
            request_type="command",
            requires_approval=False,
        )
        request.status = "input_required"
        request.missing_inputs = '["name"]'
        request.final_response = "프로젝트 이름이 필요합니다."
        db_session.commit()

        response = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "이름은 demo야"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert stub_graph_service.last_session_context == {
        "last_message_text": "프로젝트 하나 만들어줘",
        "last_request_status": "input_required",
        "last_request_type": "command",
        "last_missing_inputs": ["name"],
        "last_final_response": "프로젝트 이름이 필요합니다.",
        "last_effective_message_text": None,
        "last_resolved_references": None,
    }


def test_create_request_passes_last_effective_message_text_for_multi_turn_follow_up(db_session) -> None:
    app = create_app()
    stub_graph_service = StubGraphService(
        status="input_required",
        requires_approval=False,
        missing_inputs=["max_memory", "max_disk"],
        effective_message_text="프로젝트 하나 만들어줘\n이름은 demo야 cpu는 1이야",
    )

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub_graph_service

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "이름은 demo야 cpu는 1이야"},
        )
        assert first.status_code == 202

        second = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "메모리는 0.5야 디스크는 10이야"},
        )

    app.dependency_overrides.clear()

    assert second.status_code == 202
    assert stub_graph_service.last_session_context == {
        "last_message_text": "이름은 demo야 cpu는 1이야",
        "last_request_status": "input_required",
        "last_request_type": "command",
        "last_missing_inputs": ["max_memory", "max_disk"],
        "last_final_response": None,
        "last_effective_message_text": "프로젝트 하나 만들어줘\n이름은 demo야 cpu는 1이야",
        "last_resolved_references": None,
        "session_summary": {
            "active_goal": "이름은 demo야 cpu는 1이야",
            "recent_entities": {},
            "last_completed_task": None,
            "last_verifier_decision": None,
            "updated_at": stub_graph_service.last_session_context["session_summary"]["updated_at"],
        },
    }


def test_natural_language_approve_triggers_execution(db_session) -> None:
    """사용자가 '실행해'라고 말하면 pending_approval 요청이 승인된다."""
    app = create_app()
    stub = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘 name=demo max_cpu=1 max_memory=0.5 max_disk=10"},
        )
        assert first.json()["status"] == "pending_approval"

        second = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "실행해"},
        )

    app.dependency_overrides.clear()

    assert second.status_code == 202
    assert second.json()["status"] == "completed"
    assert second.json()["assistant_message"] == "명령 실행 완료"


def test_natural_language_reject_cancels_pending_command(db_session) -> None:
    """사용자가 '취소해'라고 말하면 pending_approval 요청이 거절된다."""
    app = create_app()
    stub = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘 name=demo max_cpu=1 max_memory=0.5 max_disk=10"},
        )
        assert first.json()["status"] == "pending_approval"

        second = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "취소해"},
        )

    app.dependency_overrides.clear()

    assert second.status_code == 202
    assert second.json()["status"] == "rejected"
    assert second.json()["assistant_message"] == "명령 실행 거절"


def test_approve_request_resumes_pending_command(client: TestClient) -> None:
    session = client.post(
        "/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()
    request = client.post(
        f"/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    ).json()

    response = client.post(
        f"/sessions/{session['session_id']}/requests/{request['request_id']}/approve",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_approve_request_returns_updated_task_snapshot(db_session) -> None:
    app = create_app()
    pending_task = {
        "kind": "operation",
        "title": "프로젝트 생성",
        "status": "pending_approval",
        "request_type": "command",
        "approval_state": "awaiting_approval",
        "operation_id": "project.create",
        "next_actions": ["approve", "edit", "cancel"],
    }
    completed_task = {
        "kind": "operation",
        "title": "프로젝트 생성",
        "status": "completed",
        "request_type": "command",
        "approval_state": "completed",
        "operation_id": "project.create",
        "next_actions": ["view_result"],
    }

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService(task_snapshot=pending_task, resumed_task_snapshot=completed_task)

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()
        request = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘"},
        ).json()

        response = client.post(
            f"/sessions/{session['session_id']}/requests/{request['request_id']}/approve",
            headers={"X-User-Id": "user-1"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["task"] is not None
    for key, value in completed_task.items():
        assert response.json()["task"][key] == value


def test_pending_high_risk_request_accepts_exact_name_reply(db_session) -> None:
    class ExactNameGraphService(StubGraphService):
        last_approval_granted: bool | str | None = None

        def resume_request(
            self,
            request_id: int,
            session_id: int,
            user_id: str,
            message_text: str,
            approval_granted: bool | str = True,
            user_role: str | None = None,
            org_id: str | None = None,
        ) -> GraphResult:
            del message_text, user_role, org_id
            self.last_approval_granted = approval_granted
            return GraphResult(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                status="completed",
                request_type="command",
                requires_approval=False,
                intent="execute_command",
                final_response="명령 실행 완료",
                selected_operation_ids=["project.delete"],
                missing_inputs=None,
            )

    graph_service = ExactNameGraphService()
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return graph_service

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()
        request = RequestRepository(db_session).create(
            session_id=session["session_id"],
            user_id="user-1",
            message_text="demo 프로젝트 삭제해줘",
            request_type="command",
            requires_approval=True,
        )
        request.status = "pending_approval"
        request.final_response = "계속하려면 대상 이름 'demo'을(를) 정확히 입력해주세요."
        db_session.commit()

        response = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "demo"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["status"] == "completed"
    assert graph_service.last_approval_granted == "demo"


def test_correction_supersedes_previous_pending_request_and_blocks_old_approval(db_session) -> None:
    app = create_app()
    stub = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘 name=demo max_cpu=1 max_memory=0.5 max_disk=10"},
        )
        assert first.status_code == 202
        assert first.json()["status"] == "pending_approval"

        second = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "아니 cpu는 2로 바꿔줘"},
        )
        assert second.status_code == 202

        repo = RequestRepository(db_session)
        first_record = repo.get_for_user(first.json()["request_id"], "user-1")
        second_record = repo.get_for_user(second.json()["request_id"], "user-1")
        assert first_record is not None
        assert second_record is not None
        assert first_record.status == RequestStatus.SUPERSEDED.value
        assert first_record.superseded_by == second_record.id
        assert second_record.status == "pending_approval"

        stale_approval = client.post(
            f"/sessions/{session['session_id']}/requests/{first_record.id}/approve",
            headers={"X-User-Id": "user-1"},
        )
        fresh_approval = client.post(
            f"/sessions/{session['session_id']}/requests/{second_record.id}/approve",
            headers={"X-User-Id": "user-1"},
        )

    app.dependency_overrides.clear()

    assert stale_approval.status_code == 409
    assert fresh_approval.status_code == 200
    assert fresh_approval.json()["status"] == "completed"


def test_reject_request_emits_rejected_event(client: TestClient) -> None:
    session = client.post(
        "/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()
    request = client.post(
        f"/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    ).json()

    response = client.post(
        f"/sessions/{session['session_id']}/requests/{request['request_id']}/reject",
        headers={"X-User-Id": "user-1"},
    )
    stream_response = client.get(
        f"/sessions/{session['session_id']}/requests/{request['request_id']}/stream",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "event: approval.rejected" in stream_response.text


def test_create_request_emits_task_snapshot_in_events(db_session) -> None:
    app = create_app()
    expected_task = {
        "kind": "operation",
        "title": "프로젝트 생성",
        "status": "pending_approval",
        "request_type": "command",
        "approval_state": "awaiting_approval",
        "operation_id": "project.create",
        "next_actions": ["approve", "edit", "cancel"],
    }

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService(task_snapshot=expected_task)

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()
        request = client.post(
            f"/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘"},
        ).json()

        events = RequestEventRepository(db_session).list_after_sequence(request["request_id"], 0)

    app.dependency_overrides.clear()

    assert len(events) >= 2
    payloads = [json.loads(event.payload) for event in events]
    for key, value in expected_task.items():
        assert payloads[0]["task"][key] == value
        assert payloads[1]["task"][key] == value
