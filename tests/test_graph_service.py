from __future__ import annotations

from dataclasses import dataclass

from chatops.graph.service import GraphService
from chatops.services.registry import RegistryEntry


@dataclass
class FakeLLMService:
    def classify(self, message_text: str) -> dict[str, object]:
        if "상태" in message_text or "트래픽" in message_text:
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

    def answer_inquiry(self, message_text: str) -> str:
        return f"문의 응답: {message_text}"

    def interpret_query_result(self, message_text: str, raw_result: dict[str, object]) -> str:
        return f"조회 응답: {raw_result['summary']}"

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        return f"실행 계획: {operation_ids[0]}"


@dataclass
class FakeRegistryService:
    def find_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[RegistryEntry]:
        if usable_in == "query":
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
                required_inputs={},
                preconditions=(),
                missing_info_questions=(),
                response_interpretation="생성 결과",
                plan_template=("입력 확인",),
                examples=(),
            )
        ]


@dataclass
class FakeAdapterService:
    def execute_query(self, operation: RegistryEntry, user_id: str) -> dict[str, object]:
        return {"summary": f"{operation.id} ok for {user_id}"}

    def execute_command(self, operation: RegistryEntry, user_id: str) -> dict[str, object]:
        return {"summary": f"{operation.id} executed for {user_id}"}


fake_graph_service = GraphService(
    llm_service=FakeLLMService(),
    registry_service=FakeRegistryService(),
    adapter_service=FakeAdapterService(),
)


def test_inquiry_completes_without_approval() -> None:
    result = fake_graph_service.handle_request(
        session_id="session-1",
        user_id="user-1",
        message_text="프로젝트 생성 방법 알려줘",
    )

    assert result.status == "completed"
    assert result.requires_approval is False


def test_query_returns_interpreted_response() -> None:
    result = fake_graph_service.handle_request(
        session_id="session-1",
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 알려줘",
    )

    assert result.status == "completed"
    assert result.final_response == "조회 응답: monitoring.get_app_deployment_traffic ok for user-1"


def test_command_request_stops_at_pending_approval() -> None:
    result = fake_graph_service.handle_request(
        session_id="session-1",
        user_id="user-1",
        message_text="프로젝트 생성해줘",
    )

    assert result.status == "pending_approval"
    assert result.requires_approval is True
    assert result.selected_operation_ids == ["project.create"]


def test_command_resume_executes_after_approval() -> None:
    result = fake_graph_service.resume_request(
        request_id="request-1",
        session_id="session-1",
        user_id="user-1",
        message_text="프로젝트 생성해줘",
    )

    assert result.status == "completed"
    assert result.requires_approval is False
    assert result.final_response == "명령 실행 응답: project.create executed for user-1"
