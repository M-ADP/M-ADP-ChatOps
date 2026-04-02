from __future__ import annotations

from datetime import datetime, timezone

from chatops.graph.service import GraphResult
from chatops.schemas.messages import ConversationMessage
from chatops.schemas.requests import RequestResponse
from chatops.schemas.runtime import (
    PlanObject,
    PlanStep,
    SessionSummary,
    SpecialistResult,
    VerifierDecision,
)
from chatops.schemas.tasks import TaskSnapshot


def test_runtime_schemas_serialize_plan_verifier_and_summary() -> None:
    plan = PlanObject(
        goal="demo 프로젝트에 api 앱 생성",
        specialist="application",
        entities={"project_name": "demo", "application_name": "api"},
        constraints={"approval_required": True},
        candidate_steps=[
            PlanStep(
                step_id="resolve-target",
                title="대상 해석",
                status="planned",
            ),
            PlanStep(
                step_id="create-app",
                title="앱 생성",
                status="planned",
                operation_id="application.create_apps",
            ),
        ],
        risk_level="medium",
        required_clarifications=["cpu", "memory", "disk"],
    )
    verifier = VerifierDecision(
        decision="clarify",
        summary="리소스 값이 더 필요합니다.",
        missing_inputs=["cpu", "memory", "disk"],
        follow_up_action="fill_inputs",
    )
    specialist = SpecialistResult(
        specialist="application",
        operation_id="application.create_apps",
        summary="애플리케이션 생성 specialist가 선택되었습니다.",
        resolved_inputs={"name": "api"},
        missing_inputs=["cpu", "memory", "disk"],
    )
    summary = SessionSummary(
        active_goal="demo 프로젝트 운영",
        recent_entities={"project_name": "demo", "application_name": "api"},
        last_completed_task="프로젝트 조회",
        last_verifier_decision="clarify",
        updated_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
    )

    assert plan.model_dump()["specialist"] == "application"
    assert plan.model_dump()["candidate_steps"][1]["operation_id"] == "application.create_apps"
    assert verifier.model_dump()["decision"] == "clarify"
    assert specialist.model_dump()["missing_inputs"] == ["cpu", "memory", "disk"]
    assert summary.model_dump()["active_goal"] == "demo 프로젝트 운영"


def test_graph_result_and_api_contracts_include_runtime_metadata() -> None:
    plan = PlanObject(
        goal="demo 프로젝트에 api 앱 생성",
        specialist="application",
        entities={"project_name": "demo", "application_name": "api"},
        candidate_steps=[
            PlanStep(
                step_id="create-app",
                title="앱 생성",
                status="planned",
                operation_id="application.create_apps",
            )
        ],
        risk_level="medium",
    )
    verifier = VerifierDecision(
        decision="success",
        summary="검증 결과 문제가 없습니다.",
        follow_up_action="complete",
    )
    specialist = SpecialistResult(
        specialist="application",
        operation_id="application.create_apps",
        summary="앱 생성 도메인을 선택했습니다.",
        resolved_inputs={"name": "api", "cpu": 1},
    )
    session_summary = SessionSummary(
        active_goal="demo 프로젝트 운영",
        recent_entities={"project_name": "demo"},
        last_completed_task="앱 상태 조회",
        last_verifier_decision="success",
        updated_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
    )

    result = GraphResult(
        request_id=2001,
        session_id=1001,
        user_id="user-1",
        status="completed",
        request_type="command",
        requires_approval=False,
        intent="execute_command",
        final_response="api 앱 생성을 완료했습니다.",
        selected_operation_ids=["application.create_apps"],
        task_snapshot={
            "title": "애플리케이션 생성",
            "status": "completed",
            "approval_state": "completed",
            "next_actions": ["view_result"],
        },
        plan_object=plan.model_dump(),
        verifier_decision=verifier.model_dump(),
        specialist_result=specialist.model_dump(),
        session_summary=session_summary.model_dump(mode="json"),
    )

    response = RequestResponse(
        request_id=2001,
        session_id=1001,
        status="completed",
        message="demo 프로젝트에 api 앱 만들어줘",
        assistant_message="api 앱 생성을 완료했습니다.",
        task=TaskSnapshot(
            title="애플리케이션 생성",
            status="completed",
            approval_state="completed",
            next_actions=["view_result"],
        ),
        plan=plan,
        verifier=verifier,
        specialist=specialist,
    )
    message = ConversationMessage(
        message_id="msg_2001",
        request_id=2001,
        role="assistant",
        type="task",
        text="api 앱 생성을 완료했습니다.",
        task=TaskSnapshot(
            title="애플리케이션 생성",
            status="completed",
            approval_state="completed",
            next_actions=["view_result"],
        ),
        plan=plan,
        verifier=verifier,
        specialist=specialist,
    )

    assert result.plan_object is not None
    assert result.verifier_decision is not None
    assert result.specialist_result is not None
    assert result.session_summary is not None
    assert response.model_dump()["plan"]["specialist"] == "application"
    assert response.model_dump()["verifier"]["decision"] == "success"
    assert message.model_dump()["specialist"]["operation_id"] == "application.create_apps"
