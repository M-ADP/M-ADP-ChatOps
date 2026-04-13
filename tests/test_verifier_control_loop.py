from __future__ import annotations

from dataclasses import dataclass, field

from chatops.graph.service import GraphService
from chatops.services.resolver import ParameterResolverService
from tests.test_graph_service import FakeLLMService, FakeRegistryService


@dataclass
class SequencedDispatcher:
    command_results: list[dict[str, object]] = field(default_factory=list)
    query_results: list[dict[str, object]] = field(default_factory=list)
    command_calls: int = 0
    query_calls: int = 0

    async def execute_command(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del operation, user_id, user_role, org_id, resolved_inputs
        index = min(self.command_calls, len(self.command_results) - 1)
        self.command_calls += 1
        return dict(self.command_results[index])

    async def execute_query(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del operation, user_id, user_role, org_id, resolved_inputs
        index = min(self.query_calls, len(self.query_results) - 1)
        self.query_calls += 1
        return dict(self.query_results[index])


@dataclass
class RetryVerifierLLM(FakeLLMService):
    def verify_execution(self, execution_result: dict[str, object], **kwargs: object) -> dict[str, object]:
        if execution_result.get("success") is False:
            return {
                "decision": "retry",
                "summary": str(execution_result.get("summary", "일시적 오류")),
                "missing_inputs": [],
                "follow_up_action": "retry",
            }
        return {
            "decision": "success",
            "summary": str(execution_result.get("summary", "성공")),
            "missing_inputs": [],
            "follow_up_action": "complete",
        }


@dataclass
class ClarifyVerifierLLM(FakeLLMService):
    interpret_calls: int = 0

    def verify_execution(self, execution_result: dict[str, object], **kwargs: object) -> dict[str, object]:
        del execution_result
        return {
            "decision": "clarify",
            "summary": "프로젝트 이름이 더 필요합니다.",
            "missing_inputs": ["project_name"],
            "follow_up_action": "fill_inputs",
        }

    def interpret_query_result(self, message_text: str, raw_result: dict[str, object]) -> str:
        self.interpret_calls += 1
        return super().interpret_query_result(message_text, raw_result)


@dataclass
class EscalateVerifierLLM(FakeLLMService):
    def verify_execution(self, execution_result: dict[str, object], **kwargs: object) -> dict[str, object]:
        return {
            "decision": "escalate",
            "summary": str(execution_result.get("summary", "권한 확인이 필요합니다.")),
            "missing_inputs": [],
            "follow_up_action": "human_review",
        }


def _build_graph_service(
    *,
    llm_service: FakeLLMService,
    dispatcher: SequencedDispatcher,
) -> GraphService:
    return GraphService(
        llm_service=llm_service,
        registry_service=FakeRegistryService(),
        adapter_service=dispatcher,
        resolver_service=ParameterResolverService(),
    )


def test_command_retry_reenters_execute_and_completes_on_second_attempt() -> None:
    graph_service = _build_graph_service(
        llm_service=RetryVerifierLLM(),
        dispatcher=SequencedDispatcher(
            command_results=[
                {"success": False, "summary": "일시적 오류", "status_code": 503},
                {"success": True, "summary": "재시도 후 성공", "status_code": 200},
            ]
        ),
    )

    pending = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )
    result = graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        approval_granted=True,
    )

    assert result.status == "completed"
    assert result.final_response == "프로젝트를 생성했습니다. 프로젝트 설정을 변경하거나 앱을 추가할 수 있습니다."
    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "success"
    assert graph_service.nodes.downstream_dispatcher.command_calls == 2


def test_query_clarify_stops_before_interpretation() -> None:
    llm_service = ClarifyVerifierLLM()
    graph_service = _build_graph_service(
        llm_service=llm_service,
        dispatcher=SequencedDispatcher(
            query_results=[
                {"success": True, "summary": "정상 응답", "status_code": 200, "result": {"summary": "정상 응답"}}
            ]
        ),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 보여줘",
    )

    assert result.status == "input_required"
    assert result.final_response == "프로젝트 이름이 더 필요합니다."
    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "clarify"
    assert llm_service.interpret_calls == 0


def test_command_escalate_marks_request_escalated() -> None:
    graph_service = _build_graph_service(
        llm_service=EscalateVerifierLLM(),
        dispatcher=SequencedDispatcher(
            command_results=[
                {"success": False, "summary": "권한이 없습니다.", "status_code": 403},
            ]
        ),
    )

    pending = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )
    result = graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        approval_granted=True,
    )

    assert result.status == "escalated"
    assert result.final_response == "권한이 없습니다."
    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "escalate"
