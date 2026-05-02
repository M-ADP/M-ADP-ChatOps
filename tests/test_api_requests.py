from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from chatops.api.routers import requests as requests_router
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
    resolved_references: dict[str, object] | None = None
    resolved_ids: dict[str, object] | None = None
    last_message_text: str | None = None
    handle_final_response: str | None = None
    resume_final_response: str | None = None

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
        self.last_message_text = message_text
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
            final_response=self.handle_final_response,
            selected_operation_ids=["project.create"],
            missing_inputs=self.missing_inputs,
            effective_message_text=self.effective_message_text,
            resolved_references=self.resolved_references,
            resolved_ids=self.resolved_ids,
            task_snapshot=self.task_snapshot,
            plan_object=self.plan_object,
            verifier_decision=self.verifier_decision,
            specialist_result=self.specialist_result,
            session_summary=self.session_summary,
        )

    def reset_session_thread(self, session_id: int) -> None:
        pass

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
            final_response=(
                self.resume_final_response
                if self.resume_final_response is not None
                else ("명령 실행 완료" if approval_granted else "명령 실행 거절")
            ),
            selected_operation_ids=["project.create"],
            missing_inputs=None,
            effective_message_text=self.effective_message_text,
            resolved_references=self.resolved_references,
            resolved_ids=self.resolved_ids,
            task_snapshot=self.resumed_task_snapshot or self.task_snapshot,
            plan_object=self.plan_object,
            verifier_decision=self.verifier_decision,
            specialist_result=self.specialist_result,
            session_summary=self.session_summary,
        )


class AsyncCommandStubGraphService(StubGraphService):
    def __init__(self, *, delay_seconds: float = 0.2, **kwargs) -> None:
        super().__init__(**kwargs)
        self.delay_seconds = delay_seconds
        self.last_request_type: str | None = None
        self.last_intent: str | None = None

    def preview_request(
        self,
        message_text: str,
        session_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del session_context
        return {
            "request_type": "command",
            "effective_message_text": message_text,
            "intent": "execute_command",
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
        request_type: str | None = None,
        intent: str | None = None,
        response_stream_handler=None,
    ) -> GraphResult:
        import time

        del org_id, response_stream_handler
        self.last_session_context = session_context
        self.last_message_text = message_text
        self.last_request_type = request_type
        self.last_intent = intent
        time.sleep(self.delay_seconds)
        return GraphResult(
            request_id=request_id or self.next_request_id,
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
            resolved_references=self.resolved_references,
            resolved_ids=self.resolved_ids,
            task_snapshot=self.task_snapshot,
            plan_object=self.plan_object,
            verifier_decision=self.verifier_decision,
            specialist_result=self.specialist_result,
            session_summary=self.session_summary,
        )


class FailingGraphService:
    def preview_request(
        self,
        message_text: str,
        session_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        raise AssertionError("easter egg requests must not reach graph preview")

    def handle_request(self, **kwargs) -> GraphResult:
        raise AssertionError("easter egg requests must not reach graph handler")


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
    response = client.get("/chatops/openapi.json")

    assert response.status_code == 200
    assert client.get("/openapi.json").status_code == 404
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
    response = client.get("/chatops/openapi.json")

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
        "/chatops/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()

    response = client.post(
        f"/chatops/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    )

    assert response.status_code == 202
    assert isinstance(response.json()["request_id"], int)
    assert response.json()["status"] in {"processing", "pending_approval"}


def test_create_request_returns_immediately_for_async_command_preview(db_session) -> None:
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return AsyncCommandStubGraphService(status="pending_approval", requires_approval=True)

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        started_at = time.monotonic()
        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘"},
        )
        elapsed = time.monotonic() - started_at

        body = response.json()
        persisted = RequestRepository(db_session).get_for_user(body["request_id"], "user-1")
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            db_session.expire_all()
            persisted = RequestRepository(db_session).get_for_user(body["request_id"], "user-1")
            if persisted is not None and persisted.status != "processing":
                break
            time.sleep(0.02)

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert elapsed < 0.15
    assert body["status"] == "processing"
    assert body["request_type"] == "command"
    assert persisted is not None
    assert persisted.status == "pending_approval"


def test_async_request_passes_preview_classification_to_graph_handler(db_session) -> None:
    app = create_app()
    graph_stub = AsyncCommandStubGraphService(status="completed", requires_approval=False, delay_seconds=0.01)

    def override_db_session():
        yield db_session

    def override_graph_service():
        return graph_stub

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘"},
        )
        body = response.json()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            db_session.expire_all()
            persisted = RequestRepository(db_session).get_for_user(body["request_id"], "user-1")
            if persisted is not None and persisted.status != "processing":
                break
            time.sleep(0.02)

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert graph_stub.last_request_type == "command"
    assert graph_stub.last_intent == "execute_command"


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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        created = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘"},
        )
        request_id = created.json()["request_id"]
        fetched = client.get(
            f"/chatops/sessions/{session['session_id']}/requests/{request_id}",
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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={"title": "runtime"},
        ).json()

        created = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
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


def test_create_request_builds_rich_session_summary_from_resolved_ids(db_session) -> None:
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return StubGraphService(
            status="completed",
            requires_approval=False,
            resolved_references={"project_name": "demo", "application_name": "api"},
            resolved_ids={"project_id": 98, "application_id": 777},
            plan_object={
                "goal": "demo 프로젝트에 api 앱 생성",
                "specialist": "application",
                "entities": {"project_name": "demo", "application_name": "api"},
                "candidate_steps": [],
            },
            task_snapshot={
                "title": "애플리케이션 생성",
                "status": "completed",
                "approval_state": "completed",
                "next_actions": ["view_result"],
            },
            verifier_decision={"decision": "success", "summary": "검증 결과 문제가 없습니다."},
        )

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={"title": "runtime"},
        ).json()

        created = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "demo 프로젝트에 api 앱 만들어줘"},
        )

    app.dependency_overrides.clear()

    session_record = SessionRepository(db_session).get_for_user(session["session_id"], "user-1")

    assert created.status_code == 202
    assert session_record is not None
    summary = json.loads(session_record.session_summary)
    assert summary["recent_entities"]["projects"][0]["resolved_id"] == 98
    assert summary["recent_entities"]["applications"][0]["resolved_id"] == 777


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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 수정해줘"},
        )

        request_id = response.json()["request_id"]
        detail = client.get(
            f"/chatops/sessions/{session['session_id']}/requests/{request_id}",
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
            "/chatops/sessions",
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
            f"/chatops/sessions/{session['session_id']}/requests",
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
        "last_task_snapshot": None,
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
            "/chatops/sessions",
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
            f"/chatops/sessions/{session['session_id']}/requests",
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
        "last_task_snapshot": None,
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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "이름은 demo야 cpu는 1이야"},
        )
        assert first.status_code == 202

        second = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
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
        "last_task_snapshot": None,
        "session_summary": {
            "active_goal": "이름은 demo야 cpu는 1이야",
            "recent_entities": {"projects": [], "applications": [], "users": []},
            "last_completed_task": None,
            "last_verifier_decision": None,
            "updated_at": stub_graph_service.last_session_context["session_summary"]["updated_at"],
        },
    }


def test_create_request_rewrites_ambiguity_numeric_follow_up_before_graph(db_session) -> None:
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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        repo = RequestRepository(db_session)
        request = repo.create(
            session_id=session["session_id"],
            user_id="user-1",
            message_text="앱 만들어줘",
            effective_message_text="앱 만들어줘",
            request_id=3101,
            request_type="command",
            requires_approval=False,
        )
        request.status = "ambiguous"
        request.task_snapshot = json.dumps(
            {
                "kind": "operation",
                "title": "작업 확인",
                "status": "ambiguous",
                "request_type": "command",
                "approval_state": "needs_clarification",
                "next_actions": ["choose_option", "cancel"],
                "clarification_type": "ambiguity",
                "follow_up_prompt": {
                    "kind": "choice",
                    "options": [
                        {"value": "프로젝트 생성", "label": "프로젝트 생성"},
                        {"value": "애플리케이션 생성", "label": "애플리케이션 생성"},
                    ],
                },
            },
            ensure_ascii=False,
        )
        request.final_response = "요청이 모호합니다. 어떤 작업을 원하시나요?\n1. 프로젝트 생성\n2. 애플리케이션 생성"
        db_session.commit()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "2"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert stub_graph_service.last_message_text == "앱 만들어줘\n애플리케이션 생성"


def test_create_request_rewrites_single_missing_input_follow_up_before_graph(db_session) -> None:
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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        repo = RequestRepository(db_session)
        request = repo.create(
            session_id=session["session_id"],
            user_id="user-1",
            message_text="애플리케이션 생성해줘",
            effective_message_text="애플리케이션 생성해줘",
            request_id=3102,
            request_type="command",
            requires_approval=False,
        )
        request.status = "input_required"
        request.missing_inputs = '["project_name"]'
        request.task_snapshot = json.dumps(
            {
                "kind": "operation",
                "title": "애플리케이션 생성",
                "status": "input_required",
                "request_type": "command",
                "approval_state": "not_ready",
                "next_actions": ["fill_inputs", "cancel"],
                "clarification_type": "missing_input",
                "missing_inputs": [{"key": "project_name", "label": "대상 프로젝트"}],
                "follow_up_prompt": {
                    "kind": "missing_input",
                    "fields": [{"key": "project_name", "label": "대상 프로젝트"}],
                },
            },
            ensure_ascii=False,
        )
        request.final_response = "대상 프로젝트를 알려주세요."
        db_session.commit()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "killblack"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert stub_graph_service.last_message_text == "project_name=killblack"


def test_create_request_handles_small_talk_without_graph_execution(db_session) -> None:
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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "안녕"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["request_type"] == "inquiry"
    assert body["assistant_message"] is not None
    assert "안녕하세요" in body["assistant_message"]
    assert stub_graph_service.last_message_text is None

def test_create_request_logs_small_talk_route_trace(db_session, caplog) -> None:
    app = create_app()
    stub_graph_service = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub_graph_service

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service
    caplog.set_level(logging.INFO, logger="chatops.decision_trace")

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "안녕"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    trace_logs = [record for record in caplog.records if record.name == "chatops.decision_trace"]
    payloads = [json.loads(record.getMessage().split(" ", 1)[1]) for record in trace_logs]
    router_payload = next(payload for payload in payloads if payload["stage"] == "conversation_router")
    assert router_payload["decision"] == "small_talk"
    assert router_payload["data"]["message_text"] == "안녕"


def test_create_request_logs_follow_up_rewrite_trace(db_session, caplog) -> None:
    app = create_app()
    stub_graph_service = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return stub_graph_service

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service
    caplog.set_level(logging.INFO, logger="chatops.decision_trace")

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        repo = RequestRepository(db_session)
        request = repo.create(
            session_id=session["session_id"],
            user_id="user-1",
            message_text="애플리케이션 생성해줘",
            effective_message_text="애플리케이션 생성해줘",
            request_id=3201,
            request_type="command",
            requires_approval=False,
        )
        request.status = "input_required"
        request.missing_inputs = '["project_name"]'
        request.task_snapshot = json.dumps(
            {
                "kind": "operation",
                "title": "애플리케이션 생성",
                "status": "input_required",
                "request_type": "command",
                "approval_state": "not_ready",
                "next_actions": ["fill_inputs", "cancel"],
                "clarification_type": "missing_input",
                "missing_inputs": [{"key": "project_name", "label": "대상 프로젝트"}],
                "follow_up_prompt": {
                    "kind": "missing_input",
                    "fields": [{"key": "project_name", "label": "대상 프로젝트"}],
                },
            },
            ensure_ascii=False,
        )
        request.final_response = "대상 프로젝트를 알려주세요."
        db_session.commit()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "killblack"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    trace_logs = [record for record in caplog.records if record.name == "chatops.decision_trace"]
    payloads = [json.loads(record.getMessage().split(" ", 1)[1]) for record in trace_logs]
    rewrite_payload = next(payload for payload in payloads if payload["stage"] == "follow_up_interpreter")
    assert rewrite_payload["decision"] == "rewritten"
    assert rewrite_payload["data"]["original_message"] == "killblack"
    assert rewrite_payload["data"]["rewritten_message"] == "project_name=killblack"


def test_create_request_returns_easter_egg_before_command_processing(db_session, monkeypatch) -> None:
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        stub = StubGraphService()
        stub.status = "completed"
        stub.requires_approval = False
        stub.next_request_id = 2001
        stub.handle_final_response = "명령 실행 완료"
        return stub

    monkeypatch.setattr(
        requests_router,
        "easter_egg_service",
        requests_router.EasterEggService({"조재민": "조재민 이스터에그"}),
    )
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "조재민 프로젝트 생성해줘"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["request_type"] == "inquiry"
    assert body["assistant_message"] == "조재민 이스터에그"
    request = RequestRepository(db_session).get_for_user(request_id=body["request_id"], user_id="user-1")
    assert request is not None
    assert request.final_response == "조재민 이스터에그"


def test_create_request_returns_easter_egg_before_graph_classification(db_session, monkeypatch) -> None:
    app = create_app()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return FailingGraphService()

    monkeypatch.setattr(
        requests_router,
        "easter_egg_service",
        requests_router.EasterEggService({"조재민": "조재민 이스터에그"}),
    )
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    with TestClient(app) as client:
        session = client.post(
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "조재민"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["request_type"] == "inquiry"
    assert body["assistant_message"] == "조재민 이스터에그"
    request = RequestRepository(db_session).get_for_user(request_id=body["request_id"], user_id="user-1")
    assert request is not None
    assert request.final_response == "조재민 이스터에그"


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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘 name=demo max_cpu=1 max_memory=0.5 max_disk=10"},
        )
        assert first.json()["status"] == "pending_approval"

        second = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "실행해"},
        )

    app.dependency_overrides.clear()

    assert second.status_code == 202
    assert second.json()["status"] == "completed"
    assert second.json()["assistant_message"] == "명령 실행 완료"
    events = RequestEventRepository(db_session).list_after_sequence(first.json()["request_id"], 0)
    event_types = [event.event_type for event in events]
    assert "execution.started" in event_types
    assert event_types.index("execution.started") < event_types.index("execution.completed")


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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘 name=demo max_cpu=1 max_memory=0.5 max_disk=10"},
        )
        assert first.json()["status"] == "pending_approval"

        second = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "취소해"},
        )

    app.dependency_overrides.clear()

    assert second.status_code == 202
    assert second.json()["status"] == "rejected"
    assert second.json()["assistant_message"] == "명령 실행 거절"


def test_approve_request_resumes_pending_command(client: TestClient) -> None:
    session = client.post(
        "/chatops/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()
    request = client.post(
        f"/chatops/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    ).json()

    response = client.post(
        f"/chatops/sessions/{session['session_id']}/requests/{request['request_id']}/approve",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    events = client.get(
        f"/chatops/sessions/{session['session_id']}/requests/{request['request_id']}/events",
        headers={"X-User-Id": "user-1"},
    ).json()["items"]
    event_types = [item["type"] for item in events]
    assert "execution.started" in event_types
    assert event_types.index("execution.started") < event_types.index("execution.completed")


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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()
        request = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘"},
        ).json()

        response = client.post(
            f"/chatops/sessions/{session['session_id']}/requests/{request['request_id']}/approve",
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
            "/chatops/sessions",
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
            f"/chatops/sessions/{session['session_id']}/requests",
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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()

        first = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "프로젝트 생성해줘 name=demo max_cpu=1 max_memory=0.5 max_disk=10"},
        )
        assert first.status_code == 202
        assert first.json()["status"] == "pending_approval"

        second = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
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
            f"/chatops/sessions/{session['session_id']}/requests/{first_record.id}/approve",
            headers={"X-User-Id": "user-1"},
        )
        fresh_approval = client.post(
            f"/chatops/sessions/{session['session_id']}/requests/{second_record.id}/approve",
            headers={"X-User-Id": "user-1"},
        )

    app.dependency_overrides.clear()

    assert stale_approval.status_code == 409
    assert fresh_approval.status_code == 200
    assert fresh_approval.json()["status"] == "completed"


def test_reject_request_emits_rejected_event(client: TestClient) -> None:
    session = client.post(
        "/chatops/sessions",
        headers={"X-User-Id": "user-1"},
        json={},
    ).json()
    request = client.post(
        f"/chatops/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    ).json()

    response = client.post(
        f"/chatops/sessions/{session['session_id']}/requests/{request['request_id']}/reject",
        headers={"X-User-Id": "user-1"},
    )
    stream_response = client.get(
        f"/chatops/sessions/{session['session_id']}/requests/{request['request_id']}/stream",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "event: approval.rejected" in stream_response.text


def test_list_requests_returns_session_requests_in_desc_order(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="운영")
    repo = RequestRepository(db_session)
    first = repo.create(session_id=session.id, user_id="user-1", message_text="첫 요청", request_id=5101, request_type="query")
    first.status = "completed"
    second = repo.create(session_id=session.id, user_id="user-1", message_text="둘째 요청", request_id=5102, request_type="command")
    second.status = "pending_approval"
    db_session.commit()

    response = client.get(
        f"/chatops/sessions/{session.id}/requests",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["request_id"] for item in body["items"]] == [5102, 5101]


def test_list_requests_filters_by_query_text(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="운영")
    repo = RequestRepository(db_session)
    first = repo.create(session_id=session.id, user_id="user-1", message_text="cpu 올려줘", request_id=5201)
    first.status = "completed"
    second = repo.create(session_id=session.id, user_id="user-1", message_text="메모리 확인", request_id=5202)
    second.status = "completed"
    db_session.commit()

    response = client.get(
        f"/chatops/sessions/{session.id}/requests",
        headers={"X-User-Id": "user-1"},
        params={"q": "cpu"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["request_id"] for item in body["items"]] == [5201]


def test_list_request_events_returns_timeline_for_request(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="운영")
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="프로젝트 생성해줘",
        request_id=5301,
    )
    event_repo = RequestEventRepository(db_session)
    event_repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=1,
        event_type="request.created",
        payload='{"type":"request.created","phase":"request"}',
    )
    event_repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=2,
        event_type="approval.required",
        payload='{"type":"approval.required","phase":"approval"}',
    )
    db_session.commit()

    response = client.get(
        f"/chatops/sessions/{session.id}/requests/{request.id}/events",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["sequence"] for item in body["items"]] == [1, 2]
    assert body["items"][1]["type"] == "approval.required"


def test_request_search_finds_message_and_response_text(client: TestClient, db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title="운영")
    repo = RequestRepository(db_session)
    first = repo.create(session_id=session.id, user_id="user-1", message_text="프로젝트 로그 보여줘", request_id=5201, request_type="query")
    first.status = "completed"
    first.final_response = "로그를 조회했습니다."
    second = repo.create(session_id=session.id, user_id="user-1", message_text="프로젝트 생성해줘", request_id=5202, request_type="command")
    second.status = "completed"
    second.final_response = "프로젝트를 생성했습니다."
    db_session.commit()

    response = client.get(
        "/chatops/requests/search",
        headers={"X-User-Id": "user-1"},
        params={"query": "로그"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["request_id"] == 5201


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
            "/chatops/sessions",
            headers={"X-User-Id": "user-1"},
            json={},
        ).json()
        request = client.post(
            f"/chatops/sessions/{session['session_id']}/requests",
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
