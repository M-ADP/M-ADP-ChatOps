"""Verifier Control Loop 검증 (Agent Loop 기반).

구 Verifier 노드(retry/clarify/escalate)는 더 이상 존재하지 않는다.
Agent Loop에서는 LLM이 tool_result를 받아 자체적으로 재시도하거나 설명한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from chatops.graph.service import GraphService
from chatops.services.registry import RegistryEntry
from tests.test_agent_loop import (
    FakeAgentLLMService,
    FakeAgentRegistryService,
    FakeAgentResolverService,
    _QUERY_ENTRY,
    _text_response,
    _tool_use_response,
)


# ---------------------------------------------------------------------------
# 승인 불필요 command 엔트리 (verifier 테스트용)
# ---------------------------------------------------------------------------

_NO_CONFIRM_ENTRY = RegistryEntry(
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
    requires_confirmation=False,
    risk_level="low",
    side_effects=("프로젝트 생성",),
    required_headers=("X-User-Id",),
    required_inputs={"headers": [], "path": [], "query": [], "body": {"required": True, "required_fields": ["name"]}},
    important_inputs={"path": [], "query": [], "body": ["name"]},
)


# ---------------------------------------------------------------------------
# SequencedDispatcher: 호출 순서에 따라 다른 결과를 반환
# ---------------------------------------------------------------------------

@dataclass
class SequencedDispatcher:
    results: list[dict] = field(default_factory=list)
    call_count: int = 0
    executed_operation_ids: list[str] = field(default_factory=list)

    def _next_result(self) -> dict:
        idx = min(self.call_count, len(self.results) - 1)
        self.call_count += 1
        return dict(self.results[idx])

    async def execute_command(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict | None = None,
    ) -> dict:
        self.executed_operation_ids.append(operation.id)
        return self._next_result()

    async def execute_query(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict | None = None,
    ) -> dict:
        self.executed_operation_ids.append(operation.id)
        return self._next_result()


def _make_no_confirm_service(
    llm: FakeAgentLLMService,
    dispatcher: SequencedDispatcher,
) -> GraphService:
    registry = FakeAgentRegistryService(entries=[_NO_CONFIRM_ENTRY])
    return GraphService(
        llm_service=llm,
        registry_service=registry,
        downstream_dispatcher=dispatcher,
        resolver_service=FakeAgentResolverService(),
        use_agent_loop=True,
    )


def _make_query_service(
    llm: FakeAgentLLMService,
    dispatcher: SequencedDispatcher,
) -> GraphService:
    registry = FakeAgentRegistryService(entries=[_QUERY_ENTRY])
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

def test_execution_failure_llm_retries_and_completes() -> None:
    """도구 실행 실패 시 LLM이 tool_result(error)를 받아 재시도하고 성공한다.

    Dispatcher: 1차 호출 → 실패(503), 2차 호출 → 성공
    LLM: tool_use(1차) → tool_use(재시도) → text("재시도 후 성공")
    """
    dispatcher = SequencedDispatcher(
        results=[
            {"success": False, "summary": "503 오류"},
            {"success": True, "summary": "재시도 성공"},
        ]
    )
    llm = FakeAgentLLMService(responses=[
        # 1차 시도
        _tool_use_response("project__create", {"name": "demo"}),
        # 1차 실패 결과를 받고 재시도
        _tool_use_response("project__create", {"name": "demo"}),
        # 2차 성공 결과를 받고 완료 메시지
        _text_response("재시도 후 성공적으로 완료했습니다."),
    ])
    service = _make_no_confirm_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=8001,
        user_id="user-1",
        message_text="프로젝트 만들어줘",
    )

    assert len(dispatcher.executed_operation_ids) == 2
    assert result.status == "completed"
    assert "성공" in result.final_response


def test_clarification_needed_llm_asks_followup() -> None:
    """도구 실행 성공 후 LLM이 추가 정보가 필요하다고 판단하여 사용자에게 질문한다.

    LLM이 tool_use 후 text response로 질문한다 (도구 재사용 없음).
    """
    dispatcher = SequencedDispatcher(
        results=[
            {"success": True, "summary": "조회 결과: 앱 목록"},
        ]
    )
    llm = FakeAgentLLMService(responses=[
        # 도구 실행
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "demo",
            "application_name": "web",
        }),
        # 결과가 모호하여 사용자에게 추가 정보 요청
        _text_response("조회 결과를 받았습니다. 어떤 앱의 상세 정보를 알려드릴까요? 확인이 필요합니다."),
    ])
    registry = FakeAgentRegistryService(entries=[_QUERY_ENTRY])
    service = GraphService(
        llm_service=llm,
        registry_service=registry,
        downstream_dispatcher=dispatcher,
        resolver_service=FakeAgentResolverService(),
        use_agent_loop=True,
    )

    result = service.handle_request(
        session_id=8002,
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 보여줘",
    )

    assert result.status == "completed"
    assert "알려드릴까요" in result.final_response or "확인" in result.final_response
    assert len(result.selected_operation_ids) > 0


def test_permission_failure_llm_explains_error() -> None:
    """도구 실행이 403 권한 오류로 실패하면 LLM이 사용자에게 권한 오류를 설명한다."""
    dispatcher = SequencedDispatcher(
        results=[
            {"success": False, "summary": "권한이 없습니다.", "status_code": 403},
        ]
    )
    llm = FakeAgentLLMService(responses=[
        # 도구 시도
        _tool_use_response("project__create", {"name": "demo"}),
        # 권한 오류를 받고 설명
        _text_response("권한이 없습니다. 관리자에게 문의하세요."),
    ])
    service = _make_no_confirm_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=8003,
        user_id="user-1",
        message_text="프로젝트 만들어줘",
    )

    assert result.status == "completed"
    assert "권한" in result.final_response
