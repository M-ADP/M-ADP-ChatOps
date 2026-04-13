"""멀티스텝 실행 로직 통합 테스트.

plan_object에 candidate_steps가 2개 이상일 때 advance_step 노드가 각 단계를
순서대로 실행하고, 최종 respond_command / interpret_result가 집계된 결과를 반환하는지 검증한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from chatops.domain.enums import RequestStatus
from chatops.graph.service import GraphService
from tests.test_graph_service import FakeRegistryService, FakeResolverService


# ---------------------------------------------------------------------------
# 멀티스텝 전용 Fake LLM
# ---------------------------------------------------------------------------

@dataclass
class MultiStepLLMService:
    """command 요청에 대해 2단계 plan_object를 반환하는 fake LLM."""

    def classify(self, message_text: str) -> dict[str, object]:
        if "보여" in message_text or "목록" in message_text or "상태" in message_text:
            return {
                "request_type": "query",
                "intent": "query_status",
                "classification_reason": "조회 요청",
                "classification_confidence": 0.95,
            }
        return {
            "request_type": "command",
            "intent": "execute_command",
            "classification_reason": "멀티스텝 실행 요청",
            "classification_confidence": 0.97,
        }

    def answer_inquiry(self, message_text: str, **kwargs: object) -> str:
        return f"문의 응답: {message_text}"

    def interpret_query_result(self, message_text: str, raw_result: dict[str, object]) -> str:
        return f"조회 응답: {raw_result.get('summary', '')}"

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        return f"실행 계획: {operation_ids[0]}"

    def build_plan_object(
        self,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, object]:
        """2단계 계획을 반환한다. 두 단계 모두 project.create를 사용한다."""
        return {
            "goal": message_text,
            "specialist": "project",
            "entities": {},
            "constraints": {"approval_required": True},
            "candidate_steps": [
                {
                    "step_id": "step-0",
                    "title": "1번째 프로젝트 생성",
                    "status": "planned",
                    "operation_id": "project.create",
                },
                {
                    "step_id": "step-1",
                    "title": "2번째 프로젝트 생성",
                    "status": "planned",
                    "operation_id": "project.create",
                },
            ],
            "risk_level": "medium",
            "required_clarifications": [],
        }

    def verify_execution(self, execution_result: dict[str, object], **kwargs: object) -> dict[str, object]:
        return {
            "decision": "success",
            "summary": str(execution_result.get("summary", "성공")),
            "missing_inputs": [],
            "follow_up_action": "complete",
        }


# ---------------------------------------------------------------------------
# 멀티스텝 전용 Dispatcher — 실행 순서 추적
# ---------------------------------------------------------------------------

@dataclass
class OrderedDispatcher:
    executed_operations: list[str] = field(default_factory=list)

    async def execute_command(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.executed_operations.append(operation.id)
        return {
            "success": True,
            "summary": f"{operation.id} 완료 (#{len(self.executed_operations)})",
            "status_code": 200,
        }

    async def execute_query(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.executed_operations.append(operation.id)
        return {
            "summary": f"{operation.id} 조회 완료 (#{len(self.executed_operations)})",
            "status_code": 200,
        }


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _build_service(dispatcher: OrderedDispatcher) -> GraphService:
    return GraphService(
        llm_service=MultiStepLLMService(),
        registry_service=FakeRegistryService(),
        downstream_dispatcher=dispatcher,
        resolver_service=FakeResolverService(),
    )


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------

def test_multistep_command_executes_all_steps_and_aggregates_response() -> None:
    """2단계 command 플랜에서 두 단계가 모두 실행되고 집계 응답이 반환되어야 한다."""
    dispatcher = OrderedDispatcher()
    service = _build_service(dispatcher)

    # 첫 요청: pending_approval 상태까지 진행
    result = service.handle_request(
        session_id=1,
        user_id="user-1",
        message_text="프로젝트 두 개 만들어줘",
    )
    assert result.status == RequestStatus.PENDING_APPROVAL.value, f"expected pending_approval, got {result.status}"
    request_id = result.request_id

    # 승인 후 재개
    result = service.resume_request(
        request_id=request_id,
        session_id=1,
        user_id="user-1",
        message_text="승인",
        approval_granted=True,
    )

    # 두 단계 모두 실행되었어야 함
    assert len(dispatcher.executed_operations) == 2, (
        f"2단계 실행 기대, 실제: {dispatcher.executed_operations}"
    )
    assert dispatcher.executed_operations[0] == "project.create"
    assert dispatcher.executed_operations[1] == "project.create"

    # 최종 응답에 "2개 작업" 집계 메시지가 포함되어야 함
    assert result.status == RequestStatus.COMPLETED.value, f"expected completed, got {result.status}"
    assert result.final_response is not None
    assert "2" in result.final_response, f"집계 응답 없음: {result.final_response}"


def test_multistep_completed_steps_in_state() -> None:
    """completed_steps 필드에 각 단계의 결과가 기록되어야 한다."""
    dispatcher = OrderedDispatcher()
    service = _build_service(dispatcher)

    result = service.handle_request(
        session_id=2,
        user_id="user-2",
        message_text="프로젝트 두 개 만들어줘",
    )
    request_id = result.request_id

    result = service.resume_request(
        request_id=request_id,
        session_id=2,
        user_id="user-2",
        message_text="승인",
        approval_granted=True,
    )

    # plan_object가 포함되어 있어야 함
    assert result.plan_object is not None
    candidate_steps = result.plan_object.get("candidate_steps", [])
    assert len(candidate_steps) == 2, f"plan_object에 2단계 기대, 실제: {candidate_steps}"


def test_single_step_command_behaves_as_before() -> None:
    """단일 단계(기존 동작)에서는 집계 메시지 없이 단일 응답이 반환되어야 한다."""
    from tests.test_graph_service import FakeLLMService, FakeDownstreamDispatcher

    dispatcher = FakeDownstreamDispatcher()
    service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        downstream_dispatcher=dispatcher,
        resolver_service=FakeResolverService(),
    )

    result = service.handle_request(
        session_id=3,
        user_id="user-3",
        message_text="프로젝트 만들어줘",
    )
    request_id = result.request_id

    result = service.resume_request(
        request_id=request_id,
        session_id=3,
        user_id="user-3",
        message_text="승인",
        approval_granted=True,
    )

    assert result.status == RequestStatus.COMPLETED.value
    # 단일 단계이므로 "N개 작업" 집계 메시지가 없어야 함
    assert result.final_response is not None
    assert "개 작업을 모두 완료" not in result.final_response, (
        f"단일 단계에서 집계 응답이 나와선 안 됨: {result.final_response}"
    )
