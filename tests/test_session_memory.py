from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from chatops.api.dependencies import get_db_session, get_graph_service
from chatops.app import create_app
from chatops.db.repositories import SessionRepository
from chatops.services.entity_memory_service import EntityMemoryService
from chatops.services.session_summary_service import SessionSummaryService


def test_session_summary_service_builds_summary_from_runtime_metadata() -> None:
    service = SessionSummaryService()

    summary = service.build(
        message_text="demo 프로젝트에 api 앱 만들어줘",
        plan_object={
            "goal": "demo 프로젝트에 api 앱 생성",
            "entities": {"project_name": "demo", "application_name": "api"},
        },
        task_snapshot={"title": "애플리케이션 생성", "status": "completed"},
        verifier_decision={"decision": "success"},
        now=datetime(2026, 4, 3, tzinfo=timezone.utc),
    )

    assert summary["active_goal"] == "demo 프로젝트에 api 앱 생성"
    assert summary["recent_entities"]["project_name"] == "demo"
    assert summary["last_completed_task"] == "애플리케이션 생성"
    assert summary["last_verifier_decision"] == "success"


def test_entity_memory_service_merges_recent_entities_into_session_context() -> None:
    service = EntityMemoryService()

    context = service.merge_into_session_context(
        session_context={"last_request_status": "completed"},
        session_summary={
            "recent_entities": {"project_name": "demo", "application_name": "api"},
        },
    )

    assert context["last_request_status"] == "completed"
    assert context["entity_memory"]["project_name"] == "demo"
    assert context["entity_memory"]["application_name"] == "api"


def test_create_request_passes_session_summary_memory_into_graph_context(db_session) -> None:
    app = create_app()

    class StubGraphService:
        last_session_context: dict[str, object] | None = None

        def handle_request(
            self,
            session_id: int,
            user_id: str,
            message_text: str,
            user_role: str | None = None,
            org_id: str | None = None,
            session_context: dict[str, object] | None = None,
        ):
            from chatops.graph.service import GraphResult

            del user_role, org_id
            self.last_session_context = session_context
            return GraphResult(
                request_id=2001,
                session_id=session_id,
                user_id=user_id,
                status="completed",
                request_type="query",
                requires_approval=False,
                intent="query_status",
                final_response="완료",
                selected_operation_ids=["project.get"],
                task_snapshot={
                    "title": "프로젝트 조회",
                    "status": "completed",
                    "approval_state": "completed",
                    "next_actions": ["refine"],
                },
            )

    graph = StubGraphService()

    def override_db_session():
        yield db_session

    def override_graph_service():
        return graph

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_graph_service] = override_graph_service

    session = SessionRepository(db_session).create(user_id="user-1", title="summary")
    session.session_summary = json.dumps(
        {
            "active_goal": "demo 프로젝트 운영",
            "recent_entities": {"project_name": "demo", "application_name": "api"},
            "last_completed_task": "앱 상태 조회",
            "last_verifier_decision": "success",
            "updated_at": "2026-04-03T00:00:00Z",
        },
        ensure_ascii=False,
    )
    db_session.commit()

    with TestClient(app) as client:
        response = client.post(
            f"/sessions/{session.id}/requests",
            headers={"X-User-Id": "user-1"},
            json={"message": "GitHub도 연결해줘"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert graph.last_session_context is not None
    assert graph.last_session_context["session_summary"]["active_goal"] == "demo 프로젝트 운영"
    assert graph.last_session_context["entity_memory"]["project_name"] == "demo"
