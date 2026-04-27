"""Agent Loop 통합 테스트.

Phase 3: inquiry → query → command 순으로 Agent Loop의 전체 플로우를 검증한다.
FakeAgentLLMService가 converse_with_tools 응답을 시뮬레이션하여
agent_reasoning → safety_gate → execute_tool 루프를 테스트한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from chatops.graph.service import GraphService
from chatops.services.registry import RegistryEntry


# ──────────────────────────────────────────────────
# Fake Services
# ──────────────────────────────────────────────────


def _make_tool_use_id() -> str:
    return f"tooluse_{uuid.uuid4().hex[:12]}"


def _text_response(text: str) -> dict[str, Any]:
    """LLM이 텍스트로만 응답 (도구 미사용 — inquiry/최종 요약)."""
    return {
        "stop_reason": "end_turn",
        "assistant_message": {
            "role": "assistant",
            "content": [{"text": text}],
        },
        "tool_calls": [],
        "text_content": text,
    }


def _tool_use_response(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """LLM이 도구 호출을 요청."""
    tool_use_id = _make_tool_use_id()
    return {
        "stop_reason": "tool_use",
        "assistant_message": {
            "role": "assistant",
            "content": [
                {
                    "toolUse": {
                        "toolUseId": tool_use_id,
                        "name": tool_name,
                        "input": tool_input,
                    }
                }
            ],
        },
        "tool_calls": [
            {
                "tool_use_id": tool_use_id,
                "name": tool_name,
                "input": tool_input,
            }
        ],
        "text_content": None,
    }


@dataclass
class FakeAgentLLMService:
    """Agent Loop용 Fake LLM. converse_with_tools 호출 시 미리 정의된 응답을 순서대로 반환한다."""

    responses: list[dict[str, Any]] = field(default_factory=list)
    call_count: int = 0
    recorded_messages: list[list[dict[str, Any]]] = field(default_factory=list)
    recorded_tool_choices: list[dict[str, Any] | None] = field(default_factory=list)

    def converse_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tool_specs: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.recorded_messages.append(list(messages))
        self.recorded_tool_choices.append(tool_choice)
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            response = _text_response("완료되었습니다.")
        self.call_count += 1
        return response

    # 기존 워크플로우 호환 메서드 (agent loop에서는 사용되지 않지만 타입 완전성을 위해)
    def classify(self, message_text: str) -> dict[str, Any]:
        return {"request_type": "inquiry", "intent": "answer_inquiry"}

    def answer_inquiry(self, message_text: str, **kwargs: Any) -> str:
        return ""

    def interpret_query_result(self, message_text: str, raw_result: dict[str, Any]) -> str:
        return ""

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        return ""

    def build_plan_object(self, message_text: str, request_type: str, candidate_operation_ids: list[str]) -> dict[str, Any]:
        return {}


# ── Registry Entries ──

_QUERY_ENTRY = RegistryEntry(
    id="monitoring.get_app_deployment_traffic",
    source_file="ai_registry/monitoring.get_app_deployment_traffic.ai.yaml",
    operation_id="get_app_deployment_traffic",
    path="/monitoring/apps/traffic",
    method="GET",
    summary="앱 트래픽 조회",
    capability="앱 트래픽 조회",
    usable_in=("query",),
    operation_kind="read",
    when_to_use=("트래픽 조회",),
    when_not_to_use=(),
    requires_confirmation=False,
    risk_level="low",
    side_effects=(),
    required_headers=("X-User-Id",),
    required_inputs={},
)

_COMMAND_ENTRY = RegistryEntry(
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
    requires_confirmation=True,
    risk_level="medium",
    side_effects=("프로젝트 생성",),
    required_headers=("X-User-Id",),
    required_inputs={
        "headers": [],
        "path": [],
        "query": [],
        "body": {"required": True, "required_fields": ["name"]},
    },
    important_inputs={"path": [], "query": [], "body": ["name", "max_cpu", "max_memory", "max_disk"]},
)

_ROLE_REQUIRED_ENTRY = RegistryEntry(
    id="project.list_projects",
    source_file="ai_registry/project.list_projects.ai.yaml",
    operation_id="list_projects",
    path="/projects",
    method="GET",
    summary="프로젝트 목록 조회",
    capability="프로젝트 목록 조회",
    usable_in=("query",),
    operation_kind="read",
    when_to_use=("프로젝트 목록 조회",),
    when_not_to_use=(),
    requires_confirmation=False,
    risk_level="low",
    side_effects=(),
    required_headers=("X-User-Id", "X-User-Role"),
    required_inputs={},
)


@dataclass
class FakeAgentRegistryService:
    """Agent Loop용 Fake Registry. all_enabled_entries와 get_entry를 지원."""

    entries: list[RegistryEntry] = field(default_factory=lambda: [_QUERY_ENTRY, _COMMAND_ENTRY])

    def all_enabled_entries(self) -> list[RegistryEntry]:
        return self.entries

    def get_entry(self, entry_id: str) -> RegistryEntry | None:
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None


@dataclass
class FakeAgentDownstreamDispatcher:
    """Agent Loop용 Fake Dispatcher. execute 호출을 기록한다."""

    last_operation_id: str | None = None
    last_resolved_inputs: dict[str, Any] | None = None
    execute_result: dict[str, Any] = field(default_factory=lambda: {"summary": "ok", "success": True})
    executed_operation_ids: list[str] = field(default_factory=list)

    async def execute_query(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.last_operation_id = operation.id
        self.last_resolved_inputs = resolved_inputs
        self.executed_operation_ids.append(operation.id)
        return dict(self.execute_result)

    async def execute_command(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.last_operation_id = operation.id
        self.last_resolved_inputs = resolved_inputs
        self.executed_operation_ids.append(operation.id)
        return dict(self.execute_result)


@dataclass
class FakeAgentResolverService:
    def resolve(
        self,
        operation: RegistryEntry,
        message_text: str,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {}


# ──────────────────────────────────────────────────
# Helper: GraphService 생성
# ──────────────────────────────────────────────────


def _make_agent_service(
    llm: FakeAgentLLMService | None = None,
    registry: FakeAgentRegistryService | None = None,
    dispatcher: FakeAgentDownstreamDispatcher | None = None,
    resolver: FakeAgentResolverService | None = None,
) -> GraphService:
    return GraphService(
        llm_service=llm or FakeAgentLLMService(),
        registry_service=registry or FakeAgentRegistryService(),
        downstream_dispatcher=dispatcher or FakeAgentDownstreamDispatcher(),
        resolver_service=resolver or FakeAgentResolverService(),
        use_agent_loop=True,
    )


# ──────────────────────────────────────────────────
# 1. Inquiry 시나리오: LLM이 도구 없이 텍스트로 직접 응답
# ──────────────────────────────────────────────────


def test_inquiry_completes_with_text_response() -> None:
    """LLM이 도구를 호출하지 않고 텍스트로 응답하면 바로 완료된다."""
    llm = FakeAgentLLMService(responses=[
        _text_response("프로젝트 생성은 '프로젝트 생성해줘'라고 말씀하시면 됩니다."),
    ])
    service = _make_agent_service(llm=llm)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 방법 알려줘",
    )

    assert result.status == "completed"
    assert result.request_type == "agent"
    assert "프로젝트 생성" in result.final_response
    assert result.requires_approval is False
    assert llm.call_count == 1


def test_query_request_forces_tool_choice_before_any_tool_execution() -> None:
    """분류된 query 요청은 첫 reasoning 호출에서 도구 호출을 강제한다."""
    llm = FakeAgentLLMService(responses=[
        _text_response("트래픽을 확인했습니다."),
    ])
    service = _make_agent_service(llm=llm)

    service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="api 트래픽 보여줘",
        request_type="query",
        intent="query_status",
    )

    assert llm.recorded_tool_choices[0] == {"any": {}}


def test_inquiry_request_uses_auto_tool_choice() -> None:
    """inquiry/chat 계열은 도구 호출을 강제하지 않는다."""
    llm = FakeAgentLLMService(responses=[
        _text_response("설명해드리겠습니다."),
    ])
    service = _make_agent_service(llm=llm)

    service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 방법 알려줘",
        request_type="inquiry",
        intent="answer_inquiry",
    )

    assert llm.recorded_tool_choices[0] == {"auto": {}}


def test_inquiry_no_tool_calls_recorded() -> None:
    """Inquiry 시 도구가 실행되지 않으므로 selected_operation_ids가 비어있다."""
    llm = FakeAgentLLMService(responses=[
        _text_response("설명해드리겠습니다."),
    ])
    service = _make_agent_service(llm=llm)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="앱 배포 방법 알려줘",
    )

    assert result.selected_operation_ids == []
    assert result.status == "completed"


# ──────────────────────────────────────────────────
# 2. Query 시나리오: 도구 호출 → 결과 요약
# ──────────────────────────────────────────────────


def test_query_tool_call_and_summary() -> None:
    """LLM이 read 도구를 호출하고, 결과를 받아 요약 텍스트로 응답한다."""
    llm = FakeAgentLLMService(responses=[
        # 1차: LLM이 도구 호출
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "alpha",
            "application_name": "web-api",
        }),
        # 2차: 도구 결과를 받은 후 텍스트로 요약
        _text_response("alpha 프로젝트의 web-api 앱 트래픽은 정상 범위입니다."),
    ])
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "트래픽 100 req/s", "success": True},
    )
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="alpha 프로젝트 web-api 앱 트래픽 알려줘",
    )

    assert result.status == "completed"
    assert "트래픽" in result.final_response
    assert result.selected_operation_ids == ["monitoring.get_app_deployment_traffic"]
    assert llm.call_count == 2
    assert dispatcher.last_operation_id == "monitoring.get_app_deployment_traffic"


def test_query_resolved_inputs_passed_to_dispatcher() -> None:
    """도구 호출 시 LLM이 제공한 파라미터가 resolved_inputs로 변환되어 dispatcher에 전달된다."""
    llm = FakeAgentLLMService(responses=[
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "beta",
            "application_name": "worker",
        }),
        _text_response("조회 완료."),
    ])
    dispatcher = FakeAgentDownstreamDispatcher()
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="beta 프로젝트 worker 앱 트래픽",
    )

    assert dispatcher.last_resolved_inputs is not None
    refs = dispatcher.last_resolved_inputs.get("references", {})
    assert refs.get("project_name") == "beta"
    assert refs.get("application_name") == "worker"


# ──────────────────────────────────────────────────
# 3. Command 시나리오: 도구 호출 + 승인 플로우
# ──────────────────────────────────────────────────


def test_command_requires_approval_interrupts() -> None:
    """requires_confirmation=True인 command 도구 호출 시 승인 대기(interrupt)에 진입한다."""
    llm = FakeAgentLLMService(responses=[
        _tool_use_response("project__create", {
            "project_name": "demo",
            "name": "demo",
            "max_cpu": 2,
            "max_memory": 4,
            "max_disk": 20,
        }),
    ])
    dispatcher = FakeAgentDownstreamDispatcher()
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 생성해줘 max_cpu=2 max_memory=4 max_disk=20",
    )

    # interrupt()가 발생하여 그래프가 중단됨 — 실행되지 않음
    assert dispatcher.last_operation_id is None
    assert result.request_type == "agent"


def test_command_approval_resume_executes() -> None:
    """승인 후 resume하면 도구가 실행되고 최종 응답이 반환된다."""
    llm = FakeAgentLLMService(responses=[
        # handle_request: LLM이 도구 호출
        _tool_use_response("project__create", {
            "project_name": "demo",
            "name": "demo",
            "max_cpu": 2,
        }),
        # resume 후 agent_reasoning: 실행 결과 받아 최종 응답
        _text_response("demo 프로젝트를 성공적으로 생성했습니다."),
    ])
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "프로젝트 생성 완료", "success": True},
    )
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    # 1단계: 승인 대기
    pending = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 생성해줘",
    )

    # 2단계: 승인 후 재개
    result = service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 생성해줘",
        approval_granted=True,
    )

    assert dispatcher.last_operation_id == "project.create"
    assert "생성" in result.final_response


# ──────────────────────────────────────────────────
# 4. 에러 시나리오
# ──────────────────────────────────────────────────


def test_unknown_tool_returns_error_to_llm() -> None:
    """존재하지 않는 도구를 호출하면 에러 tool_result가 LLM에 전달되고, LLM이 설명한다."""
    llm = FakeAgentLLMService(responses=[
        # 1차: 존재하지 않는 도구 호출
        _tool_use_response("unknown__tool", {"param": "value"}),
        # 2차: 에러를 받은 LLM이 텍스트로 설명
        _text_response("죄송합니다. 해당 기능은 지원되지 않습니다."),
    ])
    service = _make_agent_service(llm=llm)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="kubernetes 클러스터 생성해줘",
    )

    assert result.status == "completed"
    assert "지원" in result.final_response
    # 에러 후 LLM이 다시 호출되어야 함
    assert llm.call_count == 2
    # 에러 tool_result가 메시지에 포함되어야 함
    second_call_messages = llm.recorded_messages[1]
    has_error_result = any(
        "toolResult" in str(msg)
        for msg in second_call_messages
    )
    assert has_error_result


def test_auth_failure_returns_error_to_llm() -> None:
    """X-User-Role 필수인 도구를 role 없이 호출하면 차단 에러가 LLM에 전달된다."""
    registry = FakeAgentRegistryService(entries=[_ROLE_REQUIRED_ENTRY])
    llm = FakeAgentLLMService(responses=[
        _tool_use_response("project__list_projects", {}),
        _text_response("권한이 필요합니다. 관리자에게 문의해주세요."),
    ])
    service = _make_agent_service(llm=llm, registry=registry)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        user_role=None,
        message_text="프로젝트 목록 보여줘",
    )

    assert result.status == "completed"
    assert llm.call_count == 2


def test_max_iterations_prevents_infinite_loop() -> None:
    """_MAX_ITERATIONS 초과 시 안전하게 종료된다."""
    # 11개의 도구 호출 응답 (MAX_ITERATIONS=10)
    responses = [
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": f"proj-{i}",
            "application_name": "app",
        })
        for i in range(12)
    ]
    llm = FakeAgentLLMService(responses=responses)
    dispatcher = FakeAgentDownstreamDispatcher()
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="모든 프로젝트 트래픽 조회",
    )

    assert result.status == "completed"
    assert "최대 실행 횟수" in result.final_response


# ──────────────────────────────────────────────────
# 5. 멀티스텝 시나리오
# ──────────────────────────────────────────────────


def test_multistep_query_executes_multiple_tools() -> None:
    """LLM이 여러 도구를 순차적으로 호출하여 멀티스텝 작업을 수행한다."""
    llm = FakeAgentLLMService(responses=[
        # 1차: 첫 번째 도구 호출
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "alpha",
            "application_name": "api",
        }),
        # 2차: 두 번째 도구 호출
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "alpha",
            "application_name": "worker",
        }),
        # 3차: 결과 종합 요약
        _text_response("alpha 프로젝트의 api와 worker 앱 모두 트래픽이 정상입니다."),
    ])
    dispatcher = FakeAgentDownstreamDispatcher()
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="alpha 프로젝트 api랑 worker 앱 트래픽 둘 다 알려줘",
    )

    assert result.status == "completed"
    assert llm.call_count == 3
    assert len(result.selected_operation_ids) == 2


def test_execution_failure_returned_to_llm() -> None:
    """도구 실행 실패 시 에러가 tool_result로 LLM에 전달된다."""
    llm = FakeAgentLLMService(responses=[
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "gamma",
            "application_name": "web",
        }),
        _text_response("조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."),
    ])
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"success": False, "summary": "서버 오류"},
    )
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="gamma 프로젝트 web 앱 트래픽",
    )

    assert result.status == "completed"
    assert llm.call_count == 2


# ──────────────────────────────────────────────────
# 6. Multi-turn 시나리오: input_required 패턴
# ──────────────────────────────────────────────────


def test_missing_input_followup_completes() -> None:
    """LLM이 파라미터 부족 시 질문하고, 후속 메시지에서 파라미터를 받아 도구를 실행한다.

    Turn 1: "트래픽 조회해줘" → LLM: "어떤 프로젝트/앱인가요?"
    Turn 2: "alpha web-api" → LLM: tool_use → tool_result → 요약
    """
    llm = FakeAgentLLMService(responses=[
        # Turn 1 — 파라미터 부족, 질문으로 응답
        _text_response("어떤 프로젝트의 앱 트래픽을 조회할까요?"),
        # Turn 2 — 파라미터 제공 후 도구 호출
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "alpha",
            "application_name": "web-api",
        }),
        # Turn 2 — 도구 결과 요약
        _text_response("alpha 프로젝트의 web-api 앱 트래픽을 조회했습니다."),
    ])
    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "트래픽 100 req/s", "success": True},
    )
    service = _make_agent_service(llm=llm, dispatcher=dispatcher)

    # Turn 1: 파라미터 없이 요청
    turn1 = service.handle_request(
        session_id=2001,
        user_id="user-1",
        message_text="트래픽 조회해줘",
    )
    assert turn1.status == "completed"
    assert "조회" in turn1.final_response
    assert turn1.selected_operation_ids == []  # 도구 미실행
    assert llm.call_count == 1

    # Turn 2: 파라미터 제공 (동일 session_id)
    turn2 = service.handle_request(
        session_id=2001,
        user_id="user-1",
        message_text="alpha 프로젝트 web-api 앱",
    )
    assert turn2.status == "completed"
    assert "alpha" in turn2.final_response
    assert "monitoring.get_app_deployment_traffic" in turn2.selected_operation_ids
    assert llm.call_count == 3

    # Turn 2의 LLM 호출 시 이전 대화 맥락이 포함되어야 한다.
    # recorded_messages[1] = Turn 2의 첫 번째 agent_reasoning 호출
    turn2_messages = llm.recorded_messages[1]
    # 최소 3개: user(Turn1) + assistant(Turn1 질문) + user(Turn2)
    assert len(turn2_messages) >= 3


def test_session_history_visible_on_followup() -> None:
    """후속 요청에서 LLM이 받는 messages에 이전 대화 내용이 포함된다."""
    llm = FakeAgentLLMService(responses=[
        # Turn 1
        _text_response("어떤 앱인지 알려주세요."),
        # Turn 2
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "beta",
            "application_name": "api",
        }),
        _text_response("beta api 트래픽 조회 완료."),
    ])
    service = _make_agent_service(llm=llm)

    service.handle_request(session_id=3001, user_id="u1", message_text="트래픽 어때?")
    service.handle_request(session_id=3001, user_id="u1", message_text="beta 프로젝트 api 앱")

    # Turn 2의 첫 번째 agent_reasoning 호출 시 메시지 수 확인
    # [user: Turn1, assistant: Turn1 응답, user: Turn2] = 3개
    assert len(llm.recorded_messages) >= 2
    turn2_first_call_messages = llm.recorded_messages[1]
    assert len(turn2_first_call_messages) == 3


def test_different_sessions_are_isolated() -> None:
    """다른 session_id는 독립된 대화 히스토리를 가진다."""
    llm = FakeAgentLLMService(responses=[
        _text_response("세션 A 응답입니다."),
        _text_response("세션 B 응답입니다."),
    ])
    service = _make_agent_service(llm=llm)

    service.handle_request(session_id=4001, user_id="u1", message_text="안녕")
    service.handle_request(session_id=4002, user_id="u2", message_text="반가워")

    # 각 세션은 독립 thread → 상대방 메시지를 보지 않는다.
    session_a_messages = llm.recorded_messages[0]
    session_b_messages = llm.recorded_messages[1]

    assert len(session_a_messages) == 1  # 세션 A만: user: "안녕"
    assert len(session_b_messages) == 1  # 세션 B만: user: "반가워"


# ──────────────────────────────────────────────────
# 7. use_agent_loop 하위 호환 테스트
# ──────────────────────────────────────────────────


def test_use_agent_loop_flag_is_accepted_but_ignored() -> None:
    """use_agent_loop 파라미터가 하위 호환을 위해 받아들여진다 (항상 agent loop 사용)."""
    service = _make_agent_service(
        llm=FakeAgentLLMService(responses=[
            _text_response("항상 agent loop입니다."),
        ]),
    )

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="테스트",
    )

    assert result.request_type == "agent"
    assert result.status == "completed"
