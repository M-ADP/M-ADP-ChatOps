"""멀티스텝 실행 로직 통합 테스트 (Agent Loop 기반).

Agent Loop에서 LLM이 여러 도구를 순차적으로 호출하는 시나리오를 검증한다.
requires_confirmation=False인 엔트리를 사용하여 승인 없이 순차 실행을 테스트한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from chatops.graph.service import GraphService
from chatops.services.registry import RegistryEntry
from tests.test_agent_loop import (
    FakeAgentLLMService,
    FakeAgentDownstreamDispatcher,
    FakeAgentRegistryService,
    FakeAgentResolverService,
    _QUERY_ENTRY,
    _text_response,
    _tool_use_response,
    _make_agent_service,
)


# ---------------------------------------------------------------------------
# 승인 불필요(requires_confirmation=False) 명령 엔트리
# ---------------------------------------------------------------------------

_NO_CONFIRM_COMMAND_ENTRY = RegistryEntry(
    id="project.create",
    source_file="ai_registry/project.create.ai.yaml",
    operation_id="create_project",
    path="/projects",
    method="POST",
    summary="프로젝트 생성",
    capability="프로젝트 생성",
    usable_in=("command",),
    operation_kind="write",
    when_to_use=("프로젝트 생성",),
    when_not_to_use=(),
    requires_confirmation=False,  # 승인 불필요 — 멀티스텝 테스트용
    risk_level="low",
    side_effects=("프로젝트 생성",),
    required_headers=("X-User-Id",),
    required_inputs={"headers": [], "path": [], "query": [], "body": {"required": True, "required_fields": ["name"]}},
    important_inputs={"path": [], "query": [], "body": ["name"]},
)


def _make_no_confirm_service(
    llm: FakeAgentLLMService,
    dispatcher: FakeAgentDownstreamDispatcher,
) -> GraphService:
    """승인 불필요 엔트리만 포함한 GraphService를 생성한다."""
    registry = FakeAgentRegistryService(entries=[_NO_CONFIRM_COMMAND_ENTRY])
    return GraphService(
        llm_service=llm,
        registry_service=registry,
        downstream_dispatcher=dispatcher,
        resolver_service=FakeAgentResolverService(),
        use_agent_loop=True,
    )


def _make_mixed_service(
    llm: FakeAgentLLMService,
    dispatcher: FakeAgentDownstreamDispatcher,
) -> GraphService:
    """승인 불필요 command + query 엔트리가 모두 포함된 GraphService를 생성한다."""
    registry = FakeAgentRegistryService(entries=[_NO_CONFIRM_COMMAND_ENTRY, _QUERY_ENTRY])
    return GraphService(
        llm_service=llm,
        registry_service=registry,
        downstream_dispatcher=dispatcher,
        resolver_service=FakeAgentResolverService(),
        use_agent_loop=True,
    )


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------

def test_multistep_executes_all_tools_sequentially() -> None:
    """LLM이 project.create를 두 번 순차 호출하면 dispatcher가 두 번 실행된다.

    requires_confirmation=False이므로 승인 없이 바로 실행된다.
    """
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "프로젝트 생성 완료", "success": True},
    )
    llm = FakeAgentLLMService(responses=[
        # 1차: 첫 번째 프로젝트 생성
        _tool_use_response("project__create", {"name": "proj-a"}),
        # 2차: 두 번째 프로젝트 생성
        _tool_use_response("project__create", {"name": "proj-b"}),
        # 3차: 최종 요약
        _text_response("2개 프로젝트(proj-a, proj-b)를 모두 생성했습니다."),
    ])
    service = _make_no_confirm_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=7001,
        user_id="user-1",
        message_text="프로젝트 두 개 만들어줘",
    )

    assert len(dispatcher.executed_operation_ids) == 2
    assert dispatcher.executed_operation_ids[0] == "project.create"
    assert dispatcher.executed_operation_ids[1] == "project.create"
    assert result.status == "completed"
    assert "2" in result.final_response


def test_multistep_selected_operation_ids_tracks_all_executions() -> None:
    """멀티스텝 실행 시 selected_operation_ids에 모든 실행 operation_id가 기록된다."""
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "완료", "success": True},
    )
    llm = FakeAgentLLMService(responses=[
        _tool_use_response("project__create", {"name": "proj-a"}),
        _tool_use_response("project__create", {"name": "proj-b"}),
        _text_response("2개 프로젝트를 생성했습니다."),
    ])
    service = _make_no_confirm_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=7002,
        user_id="user-1",
        message_text="프로젝트 두 개 만들어줘",
    )

    assert len(result.selected_operation_ids) == 2


def test_single_tool_call_completes_without_aggregation() -> None:
    """단일 도구 호출(requires_confirmation=False) → selected_operation_ids 길이 1, 정상 응답."""
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "프로젝트 생성 완료", "success": True},
    )
    llm = FakeAgentLLMService(responses=[
        _tool_use_response("project__create", {"name": "proj-single"}),
        _text_response("proj-single 프로젝트를 생성했습니다."),
    ])
    service = _make_no_confirm_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=7003,
        user_id="user-1",
        message_text="프로젝트 하나 만들어줘",
    )

    assert len(result.selected_operation_ids) == 1
    assert result.status == "completed"
    assert result.final_response is not None


def test_multistep_executes_in_llm_specified_order() -> None:
    """LLM이 project.create → monitoring.get_app_deployment_traffic 순서로 호출하면
    dispatcher.executed_operation_ids도 동일 순서여야 한다."""
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "완료", "success": True},
    )
    llm = FakeAgentLLMService(responses=[
        # 1차: project.create
        _tool_use_response("project__create", {"name": "proj-order"}),
        # 2차: monitoring query
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "proj-order",
            "application_name": "web",
        }),
        # 3차: 최종 요약
        _text_response("프로젝트 생성 후 트래픽을 조회했습니다."),
    ])
    service = _make_mixed_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=7004,
        user_id="user-1",
        message_text="프로젝트 만들고 트래픽 조회해줘",
    )

    assert dispatcher.executed_operation_ids == [
        "project.create",
        "monitoring.get_app_deployment_traffic",
    ]
    assert result.status == "completed"
