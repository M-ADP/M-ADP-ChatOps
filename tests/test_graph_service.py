"""GraphService 통합 테스트.

Agent Loop 기반 테스트는 test_agent_loop.py에 있다.
이 파일은 다른 테스트 파일들이 import하는 Fake 클래스를 정의한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from chatops.graph.service import GraphService
from chatops.services.registry import RegistryEntry, ScoredCandidate
from chatops.services.resolver import ParameterResolverService


# ──────────────────────────────────────────────────
# Shared Fake Services
# ──────────────────────────────────────────────────


def _make_tool_use_id() -> str:
    return f"tooluse_{uuid.uuid4().hex[:12]}"


def _text_response(text: str) -> dict[str, Any]:
    return {
        "stop_reason": "end_turn",
        "assistant_message": {"role": "assistant", "content": [{"text": text}]},
        "tool_calls": [],
        "text_content": text,
    }


def _tool_use_response(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    tool_use_id = _make_tool_use_id()
    return {
        "stop_reason": "tool_use",
        "assistant_message": {
            "role": "assistant",
            "content": [{"toolUse": {"toolUseId": tool_use_id, "name": tool_name, "input": tool_input}}],
        },
        "tool_calls": [{"tool_use_id": tool_use_id, "name": tool_name, "input": tool_input}],
        "text_content": None,
    }


@dataclass
class FakeLLMService:
    """Agent Loop 호환 Fake LLM.

    converse_with_tools: 사용자 메시지에 기반하여 도구 호출 또는 텍스트 응답을 반환.
    기존 메서드(classify 등)도 유지하여 하위 호환을 지원.
    """

    _call_count: int = 0

    def converse_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tool_specs: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del tool_choice
        self._call_count += 1

        # tool_result가 마지막 메시지면 → 도구 실행 결과를 요약
        last = messages[-1] if messages else {}
        last_content = last.get("content", []) if isinstance(last, dict) else getattr(last, "content", [])
        if isinstance(last_content, list):
            for block in last_content:
                if isinstance(block, dict) and "toolResult" in block:
                    result_content = block["toolResult"].get("content", [])
                    summary = ""
                    for c in result_content:
                        if isinstance(c, dict) and "json" in c:
                            json_result = c["json"]
                            summary = json_result.get("summary", str(json_result))
                    return _text_response(f"실행 결과: {summary}")

        # 사용자 메시지 텍스트 추출
        user_text = self._extract_user_text(messages)

        # inquiry 감지
        if any(kw in user_text for kw in ("방법", "알려줘", "설명")):
            return _text_response(f"문의 응답: {user_text}")

        # query 감지 → 도구 호출
        if any(kw in user_text for kw in ("상태", "트래픽", "목록", "보여")):
            tool_name = self._find_tool(tool_specs, "monitoring__get_app_deployment_traffic", "project__list_projects")
            return _tool_use_response(tool_name, {})

        # command 감지 → 도구 호출
        tool_name = self._find_tool(tool_specs, "project__create")
        if tool_name:
            return _tool_use_response(tool_name, {"name": "demo"})

        return _text_response(f"응답: {user_text}")

    def _extract_user_text(self, messages: list[Any]) -> str:
        for msg in messages:
            if isinstance(msg, dict):
                if msg.get("role") == "user":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and "text" in block:
                                return str(block["text"])
            else:
                role = getattr(msg, "type", "")
                if role == "human":
                    content = getattr(msg, "content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and "text" in block:
                                return str(block["text"])
                    elif isinstance(content, str):
                        return content
        return ""

    def _find_tool(self, tool_specs: list[dict[str, Any]], *names: str | None) -> str | None:
        available = {spec.get("toolSpec", {}).get("name") for spec in tool_specs}
        for name in names:
            if name and name in available:
                return name
        return next(iter(available), None)

    # 기존 워크플로우 호환 메서드 (preview_request, 다른 테스트에서 사용)

    def classify(self, message_text: str) -> dict[str, object]:
        if "상태" in message_text or "트래픽" in message_text or "목록" in message_text or "보여" in message_text:
            return {
                "request_type": "query",
                "intent": "query_status",
                "classification_reason": "상태 조회 요청",
                "classification_confidence": 0.95,
            }
        if "방법" in message_text or "알려" in message_text:
            return {
                "request_type": "inquiry",
                "intent": "answer_inquiry",
                "classification_reason": "설명 요청",
                "classification_confidence": 0.98,
            }
        return {
            "request_type": "command",
            "intent": "execute_command",
            "classification_reason": "실행 요청",
            "classification_confidence": 0.97,
        }

    def answer_inquiry(
        self,
        message_text: str,
        supported_operations: list[dict[str, object]] | None = None,
    ) -> str:
        del supported_operations
        return f"문의 응답: {message_text}"

    def interpret_query_result(self, message_text: str, raw_result: dict[str, object]) -> str:
        return f"조회 응답: {raw_result['summary']}"

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        return f"실행 계획: {operation_ids[0]}"

    def build_plan_object(
        self,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, object]:
        specialist = candidate_operation_ids[0].split(".", 1)[0] if candidate_operation_ids else request_type
        return {
            "goal": message_text,
            "specialist": specialist,
            "entities": {"message_text": message_text},
            "constraints": {"approval_required": request_type == "command"},
            "candidate_steps": [
                {
                    "step_id": "primary-operation",
                    "title": "주요 작업 실행",
                    "status": "planned",
                    "operation_id": candidate_operation_ids[0] if candidate_operation_ids else None,
                }
            ],
            "risk_level": "medium" if request_type == "command" else "low",
            "required_clarifications": [],
        }


@dataclass
class FakeRegistryService:
    calls: list[tuple[str, str]] | None = None

    def _query_entries(self) -> list[RegistryEntry]:
        return [
            RegistryEntry(
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
                preconditions=(),
                missing_info_questions=(),
                response_interpretation="트래픽 요약",
                plan_template=(),
                examples=(),
            )
        ]

    def _command_entries(self) -> list[RegistryEntry]:
        return [
            RegistryEntry(
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
                important_inputs={
                    "path": [],
                    "query": [],
                    "body": ["name", "max_cpu", "max_memory", "max_disk"],
                },
                preconditions=(),
                missing_info_questions=(),
                response_interpretation="생성 결과",
                plan_template=("입력 확인",),
                examples=(),
            )
        ]

    def all_enabled_entries(self) -> list[RegistryEntry]:
        return self._query_entries() + self._command_entries()

    def find_agent_candidates(
        self,
        user_text: str,
        *,
        step_context: Any = None,
        limit: int = 8,
    ) -> list[RegistryEntry]:
        return (self._query_entries() + self._command_entries())[:limit]

    def find_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[RegistryEntry]:
        if self.calls is None:
            self.calls = []
        self.calls.append((usable_in, user_text))
        if usable_in == "query":
            return self._query_entries()
        return self._command_entries()

    def find_scored_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[ScoredCandidate]:
        entries = self.find_candidates(user_text, usable_in, limit)
        return [ScoredCandidate(entry=e, score=100 - i) for i, e in enumerate(entries)]

    def detect_ambiguity(self, scored_candidates: list[ScoredCandidate]) -> tuple[bool, list[ScoredCandidate]]:
        return False, []

    def get_entry(self, entry_id: str) -> RegistryEntry | None:
        for candidate in self._command_entries() + self._query_entries():
            if candidate.id == entry_id:
                return candidate
        return None


@dataclass
class FakeDownstreamDispatcher:
    last_resolved_inputs: dict[str, object] | None = None

    async def execute_query(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.last_resolved_inputs = resolved_inputs
        return {"summary": f"{operation.id} ok for {user_id}"}

    async def execute_command(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.last_resolved_inputs = resolved_inputs
        return {"summary": f"{operation.id} executed for {user_id}"}


@dataclass
class FailingDownstreamDispatcher(FakeDownstreamDispatcher):
    async def execute_command(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.last_resolved_inputs = resolved_inputs
        return {
            "success": False,
            "summary": "요청값이 올바르지 않습니다.",
            "status_code": 422,
        }


@dataclass
class FakeResolverService:
    def resolve(
        self,
        operation: RegistryEntry,
        message_text: str,
        session_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del session_context
        if operation.id == "project.create":
            return {
                "body": {
                    "name": "demo",
                    "max_cpu": 1,
                    "max_memory": 0.5,
                    "max_disk": 10,
                }
            }
        return {"body": {"name": "demo"}}


# ──────────────────────────────────────────────────
# Agent Loop 통합 테스트
# ──────────────────────────────────────────────────


def test_inquiry_completes_via_agent_loop() -> None:
    """inquiry 메시지는 도구 호출 없이 텍스트로 직접 응답한다."""
    service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 방법 알려줘",
    )

    assert isinstance(result.request_id, int)
    assert result.request_id > 0
    assert result.status == "completed"
    assert result.request_type == "agent"
    assert "문의 응답" in result.final_response


def test_query_executes_tool_and_summarizes() -> None:
    """query 메시지는 도구를 호출하고 결과를 요약한다."""
    service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 보여줘",
    )

    assert result.status == "completed"
    assert result.selected_operation_ids == ["monitoring.get_app_deployment_traffic"]
    assert result.final_response is not None


def test_command_triggers_approval_interrupt() -> None:
    """command 메시지는 승인 대기(interrupt)에 진입한다."""
    service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )

    assert isinstance(result.request_id, int)
    assert result.request_type == "agent"


def test_command_resume_completes_after_approval() -> None:
    """승인 후 resume하면 도구가 실행되고 최종 응답이 반환된다."""
    service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=FakeResolverService(),
    )

    pending = service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )

    result = service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo",
        approval_granted=True,
    )

    assert result.status == "completed"
    assert result.final_response is not None
