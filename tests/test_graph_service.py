from __future__ import annotations

from dataclasses import dataclass

from chatops.domain.enums import RequestStatus
from chatops.graph.service import GraphService
from chatops.services.registry import RegistryEntry, ScoredCandidate
from chatops.services.registry import RegistryService
from chatops.services.resolver import ParameterResolverService


@dataclass
class FakeLLMService:
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


fake_graph_service = GraphService(
    llm_service=FakeLLMService(),
    registry_service=FakeRegistryService(),
    adapter_service=FakeDownstreamDispatcher(),
    resolver_service=ParameterResolverService(),
)


def test_inquiry_completes_without_approval() -> None:
    result = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 방법 알려줘",
    )

    assert isinstance(result.request_id, int)
    assert result.request_id > 0
    assert result.status == "completed"
    assert result.requires_approval is False


def test_query_returns_interpreted_response() -> None:
    result = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 알려줘",
    )

    assert isinstance(result.request_id, int)
    assert result.status == "completed"
    assert result.final_response == "조회 응답: monitoring.get_app_deployment_traffic ok for user-1"
    assert result.clarification_type is None
    assert result.fallback_used is False


def test_query_result_exposes_completed_task_snapshot() -> None:
    result = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 알려줘",
    )

    assert result.task_snapshot is not None
    assert result.task_snapshot["title"] == "앱 트래픽 조회"
    assert result.task_snapshot["status"] == "completed"
    assert result.task_snapshot["approval_state"] == "completed"
    assert result.task_snapshot["next_actions"] == ["refine", "compare", "export"]


def test_query_result_exposes_plan_and_specialist_metadata() -> None:
    result = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 알려줘",
    )

    assert result.plan_object is not None
    assert result.plan_object["specialist"] == "monitoring"
    assert result.specialist_result is not None
    assert result.specialist_result["specialist"] == "monitoring"
    assert result.specialist_result["operation_id"] == "monitoring.get_app_deployment_traffic"
    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "success"


def test_query_downstream_permission_failure_escalates() -> None:
    class QueryFailingDispatcher(FakeDownstreamDispatcher):
        async def execute_query(
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
                "summary": "실행 권한이 없습니다.",
                "status_code": 403,
            }

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=QueryFailingDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 알려줘",
    )

    assert result.status == "escalated"
    assert result.final_response == "실행 권한이 없습니다."
    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "escalate"
    assert result.task_snapshot is not None
    assert result.task_snapshot["status"] == "escalated"


def test_query_missing_required_role_header_fails_before_dispatch() -> None:
    class RoleRequiredQueryRegistry(FakeRegistryService):
        def _query_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
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
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="조회 결과",
                    plan_template=(),
                    examples=(),
                )
            ]

    dispatcher = FakeDownstreamDispatcher()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=RoleRequiredQueryRegistry(),
        adapter_service=dispatcher,
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        user_role=None,
        message_text="프로젝트 목록 보여줘",
    )

    assert result.status == "failed"
    assert result.error_code == "AUTH_CONTEXT_MISSING"
    assert "X-User-Role" in str(result.final_response)
    assert dispatcher.last_resolved_inputs is None


def test_command_request_stops_at_pending_approval() -> None:
    result = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )

    assert isinstance(result.request_id, int)
    assert result.status == "pending_approval"
    assert result.requires_approval is True
    assert result.selected_operation_ids == ["project.create"]


def test_command_request_exposes_task_snapshot() -> None:
    result = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )

    assert result.task_snapshot is not None
    assert result.task_snapshot["title"] == "프로젝트 생성"
    assert result.task_snapshot["operation_id"] == "project.create"
    assert result.task_snapshot["approval_state"] == "awaiting_approval"
    assert result.task_snapshot["target"] == {"project_name": "demo"}
    assert result.task_snapshot["filled_inputs"]["name"] == "demo"
    assert result.task_snapshot["filled_inputs"]["max_cpu"] == 1
    assert result.task_snapshot["missing_inputs"] in (None, [])
    assert result.task_snapshot["next_actions"] == ["approve", "edit", "cancel"]


def test_command_request_exposes_plan_and_specialist_metadata() -> None:
    result = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )

    assert result.plan_object is not None
    assert result.plan_object["specialist"] == "project"
    assert result.specialist_result is not None
    assert result.specialist_result["specialist"] == "project"
    assert result.specialist_result["operation_id"] == "project.create"


def test_command_resume_exposes_verifier_decision() -> None:
    pending = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )
    result = fake_graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        approval_granted=True,
    )

    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "success"


def test_command_missing_required_role_header_fails_before_approval() -> None:
    class RoleRequiredCommandRegistry(FakeRegistryService):
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
                    required_headers=("X-User-Id", "X-User-Role"),
                    required_inputs={
                        "headers": [],
                        "path": [],
                        "query": [],
                        "body": {"required": True, "required_fields": ["name"]},
                    },
                    important_inputs={"path": [], "query": [], "body": ["name"]},
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="생성 결과",
                    plan_template=("입력 확인",),
                    examples=(),
                )
            ]

    dispatcher = FakeDownstreamDispatcher()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=RoleRequiredCommandRegistry(),
        adapter_service=dispatcher,
        resolver_service=FakeResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        user_role=None,
        message_text="프로젝트 생성 name=demo",
    )

    assert result.status == "failed"
    assert result.error_code == "AUTH_CONTEXT_MISSING"
    assert "X-User-Role" in str(result.final_response)
    assert dispatcher.last_resolved_inputs is None


def test_command_resume_executes_after_approval() -> None:
    pending = fake_graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )
    result = fake_graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        approval_granted=True,
    )

    assert result.status == "completed"
    assert result.requires_approval is False
    assert result.final_response == "프로젝트를 생성했습니다. 프로젝트 설정을 변경하거나 앱을 추가할 수 있습니다."
    assert result.task_snapshot is not None
    assert result.task_snapshot["status"] == "completed"
    assert result.task_snapshot["approval_state"] == "completed"
    assert result.task_snapshot["next_actions"] == ["view_result"]


def test_command_resume_passes_resolved_inputs_to_adapter() -> None:
    adapter_service = FakeDownstreamDispatcher()
    registry_service = FakeRegistryService()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=registry_service,
        adapter_service=adapter_service,
        resolver_service=FakeResolverService(),
    )

    pending = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
    )
    graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        approval_granted=True,
    )

    assert adapter_service.last_resolved_inputs == {
        "body": {"name": "demo", "max_cpu": 1, "max_memory": 0.5, "max_disk": 10}
    }
    # planner와 command_planner 모두 registry를 호출하므로 2회
    assert registry_service.calls is not None
    assert ("command", "프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10") in registry_service.calls


def test_command_resume_rejects_without_replanning() -> None:
    registry_service = FakeRegistryService()
    adapter_service = FakeDownstreamDispatcher()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=registry_service,
        adapter_service=adapter_service,
        resolver_service=FakeResolverService(),
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
        approval_granted=False,
    )

    assert result.status == "rejected"
    assert adapter_service.last_resolved_inputs is None
    # planner와 command_planner 모두 registry를 호출하므로 호출 포함 여부만 확인
    assert registry_service.calls is not None
    assert ("command", "프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10") in registry_service.calls


def test_high_risk_command_requires_exact_name_confirmation() -> None:
    class DeleteRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="project.delete",
                    source_file="ai_registry/project.delete.ai.yaml",
                    operation_id="delete_project",
                    path="/projects/{project_id}",
                    method="DELETE",
                    summary="프로젝트 삭제",
                    capability="프로젝트 삭제",
                    usable_in=("command",),
                    operation_kind="delete",
                    when_to_use=("프로젝트 삭제",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="high",
                    side_effects=("프로젝트 삭제",),
                    required_headers=("X-User-Id",),
                    required_inputs={
                        "headers": [],
                        "path": [{"name": "project_id", "required": True}],
                        "query": [],
                        "body": None,
                    },
                    important_inputs={"path": [], "query": [], "body": []},
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="삭제 결과",
                    plan_template=("입력 확인",),
                    examples=(),
                )
            ]

    class DeleteResolverService:
        def resolve(
            self,
            operation: RegistryEntry,
            message_text: str,
            session_context: dict[str, object] | None = None,
        ) -> dict[str, object]:
            del operation, message_text, session_context
            return {"references": {"project_name": "demo"}}

    dispatcher = FakeDownstreamDispatcher()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=DeleteRegistry(),
        adapter_service=dispatcher,
        resolver_service=DeleteResolverService(),
    )

    pending = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 삭제해줘",
    )

    assert pending.status == "pending_approval"
    assert pending.final_response is not None
    assert "정확히 입력" in pending.final_response

    rejected = graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 삭제해줘",
        approval_granted="wrong-name",
    )

    assert rejected.status == "rejected"
    assert dispatcher.last_resolved_inputs is None

    pending = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 삭제해줘",
    )
    approved = graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 삭제해줘",
        approval_granted="demo",
    )

    assert approved.status == "completed"
    assert dispatcher.last_resolved_inputs == {"references": {"project_name": "demo"}}


def test_high_risk_member_removal_requires_structured_confirmation() -> None:
    class RemoveMemberRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="project.remove_member",
                    source_file="ai_registry/project.remove_member.ai.yaml",
                    operation_id="remove_project_member",
                    path="/projects/{project_id}/members/{target_user_id}",
                    method="DELETE",
                    summary="프로젝트 멤버 제거",
                    capability="프로젝트 멤버 제거",
                    usable_in=("command",),
                    operation_kind="delete",
                    when_to_use=("프로젝트 멤버 제거",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="high",
                    side_effects=("프로젝트 멤버 제거",),
                    required_headers=("X-User-Id",),
                    required_inputs={
                        "headers": [],
                        "path": [
                            {"name": "project_id", "required": True},
                            {"name": "target_user_id", "required": True},
                        ],
                        "query": [],
                        "body": None,
                    },
                    important_inputs={"path": [], "query": [], "body": []},
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="멤버 제거 결과",
                    plan_template=("입력 확인",),
                    examples=(),
                )
            ]

    class RemoveMemberResolverService:
        def resolve(
            self,
            operation: RegistryEntry,
            message_text: str,
            session_context: dict[str, object] | None = None,
        ) -> dict[str, object]:
            del operation, message_text, session_context
            return {"references": {"project_name": "demo", "target_nickname": "alice"}}

    dispatcher = FakeDownstreamDispatcher()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=RemoveMemberRegistry(),
        adapter_service=dispatcher,
        resolver_service=RemoveMemberResolverService(),
    )

    pending = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트에서 alice 멤버 제거해줘",
    )

    assert pending.status == "pending_approval"
    assert pending.final_response is not None
    assert '"project_name": "demo"' in pending.final_response
    assert '"target_user": "alice"' in pending.final_response

    rejected = graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트에서 alice 멤버 제거해줘",
        approval_granted='{"operation":"project.remove_member","project_name":"demo"}',
    )

    assert rejected.status == "rejected"
    assert dispatcher.last_resolved_inputs is None

    pending = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트에서 alice 멤버 제거해줘",
    )

    approved = graph_service.resume_request(
        request_id=pending.request_id,
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트에서 alice 멤버 제거해줘",
        approval_granted='{"operation":"project.remove_member","project_name":"demo","target_user":"alice"}',
    )

    assert approved.status == "completed"
    assert dispatcher.last_resolved_inputs == {"references": {"project_name": "demo", "target_nickname": "alice"}}


def test_query_ambiguity_returns_clarification_without_dispatch() -> None:
    class AmbiguousQueryRegistry(FakeRegistryService):
        def _query_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="project.get",
                    source_file="ai_registry/project.get.ai.yaml",
                    operation_id="get_project",
                    path="/projects/{project_id}",
                    method="GET",
                    summary="프로젝트 상태 조회",
                    capability="프로젝트 상태 조회",
                    usable_in=("query",),
                    operation_kind="read",
                    when_to_use=("프로젝트 상태",),
                    when_not_to_use=(),
                    requires_confirmation=False,
                    risk_level="low",
                    side_effects=(),
                    required_headers=("X-User-Id",),
                    required_inputs={"headers": [], "path": [{"name": "project_id", "required": True}], "query": [], "body": None},
                    important_inputs={"path": [], "query": [], "body": []},
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="조회 결과",
                    plan_template=(),
                    examples=(),
                ),
                RegistryEntry(
                    id="application.get_apps_status",
                    source_file="ai_registry/application.get_apps_status.ai.yaml",
                    operation_id="get_apps_status",
                    path="/apps/status",
                    method="GET",
                    summary="앱 상태 조회",
                    capability="앱 상태 조회",
                    usable_in=("query",),
                    operation_kind="read",
                    when_to_use=("앱 상태",),
                    when_not_to_use=(),
                    requires_confirmation=False,
                    risk_level="low",
                    side_effects=(),
                    required_headers=("X-User-Id",),
                    required_inputs={"headers": [], "path": [], "query": [], "body": None},
                    important_inputs={"path": [{"name": "project_id"}, {"name": "application_id"}], "query": [], "body": []},
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="조회 결과",
                    plan_template=(),
                    examples=(),
                ),
            ]

        def detect_ambiguity(self, scored_candidates: list[ScoredCandidate]) -> tuple[bool, list[ScoredCandidate]]:
            return True, scored_candidates[:2]

    dispatcher = FakeDownstreamDispatcher()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=AmbiguousQueryRegistry(),
        adapter_service=dispatcher,
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 상태 보여줘",
    )

    assert result.status == RequestStatus.AMBIGUOUS.value
    assert result.error_code == "AMBIGUOUS_OPERATION"
    assert result.final_response == "프로젝트 상태인가요, 앱 상태인가요?"
    assert result.clarification_type == "ambiguity"
    assert result.task_snapshot is not None
    assert result.task_snapshot["title"] == "작업 확인"
    assert result.task_snapshot["follow_up_prompt"]["kind"] == "choice"
    assert result.task_snapshot["follow_up_prompt"]["options"][1]["label"] == "앱 상태 조회"
    assert dispatcher.last_resolved_inputs is None


def test_query_missing_inputs_asks_before_dispatch() -> None:
    class AppStatusQueryRegistry(FakeRegistryService):
        def _query_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="application.get_apps_status",
                    source_file="ai_registry/application.get_apps_status.ai.yaml",
                    operation_id="get_apps_status",
                    path="/apps/status",
                    method="GET",
                    summary="앱 상태 조회",
                    capability="앱 상태 조회",
                    usable_in=("query",),
                    operation_kind="read",
                    when_to_use=("앱 상태",),
                    when_not_to_use=(),
                    requires_confirmation=False,
                    risk_level="low",
                    side_effects=(),
                    required_headers=("X-User-Id",),
                    required_inputs={"headers": [], "path": [], "query": [], "body": None},
                    important_inputs={"path": [{"name": "project_id"}, {"name": "application_id"}], "query": [], "body": []},
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="조회 결과",
                    plan_template=(),
                    examples=(),
                )
            ]

    dispatcher = FakeDownstreamDispatcher()
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=AppStatusQueryRegistry(),
        adapter_service=dispatcher,
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="앱 상태 보여줘",
    )

    assert result.status == RequestStatus.INPUT_REQUIRED.value
    assert result.missing_inputs == ["project_name", "application_name"]
    assert result.final_response == "어느 프로젝트의 어떤 앱인지 알려주세요."
    assert result.clarification_type == "missing_input"
    assert result.task_snapshot is not None
    assert result.task_snapshot["follow_up_prompt"]["kind"] == "missing_input"
    assert [field["key"] for field in result.task_snapshot["follow_up_prompt"]["fields"]] == [
        "project_name",
        "application_name",
    ]
    assert dispatcher.last_resolved_inputs is None


def test_input_required_follow_up_message_continues_previous_command() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
        session_context={
            "last_message_text": "프로젝트 하나 만들어줘",
            "last_request_status": "input_required",
            "last_request_type": "command",
        },
    )

    assert result.status == "pending_approval"
    assert result.requires_approval is True
    assert result.final_response is not None
    assert "실행할까요" in result.final_response
    assert "project.create" not in result.final_response
    assert "프로젝트 이름 demo" in result.final_response


def test_graph_service_normalizes_colloquial_application_create_request() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=RegistryService.from_directory("ai_registry"),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="어플 생성해줘ㅡ",
    )

    assert result.status == "input_required"
    assert result.task_snapshot is not None
    assert result.task_snapshot["operation_id"] == "application.create_apps"
    assert result.effective_message_text == "앱 생성해줘"


def test_graph_service_normalizes_project_shorthand_query() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=RegistryService.from_directory("ai_registry"),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프젝 목록 보여줘",
        user_role="admin",
    )

    assert result.status == "completed"
    assert result.task_snapshot is not None
    assert result.task_snapshot["operation_id"] == "project.list_projects"
    assert result.effective_message_text == "프로젝트 목록 보여줘"


def test_input_required_message_is_conversational_question() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 하나 만들어줘",
    )

    assert result.status == "input_required"
    assert result.final_response == "프로젝트를 만들려면 아래 정보가 더 필요합니다. 프로젝트 이름, 최대 CPU, 최대 메모리, 최대 디스크를 알려주세요."


def test_new_request_after_input_required_does_not_force_previous_command() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 목록 보여줘",
        session_context={
            "last_message_text": "프로젝트 하나 만들어줘",
            "last_request_status": "input_required",
            "last_request_type": "command",
        },
    )

    assert result.status == "completed"
    assert result.request_type == "query"


def test_command_without_required_inputs_returns_input_required() -> None:
    registry_service = FakeRegistryService()
    registry_service._command_entries = lambda: [
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
            missing_info_questions=("요청 본문의 name 값을 확인해야 합니다.",),
            response_interpretation="생성 결과",
            plan_template=("입력 확인",),
            examples=(),
        )
    ]
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=registry_service,
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 하나 만들어줘",
    )

    assert result.status == "input_required"
    assert result.requires_approval is False
    assert result.missing_inputs == ["name", "max_cpu", "max_memory", "max_disk"]
    assert "최대 CPU" in str(result.final_response)
    assert "최대 메모리" in str(result.final_response)
    assert "최대 디스크" in str(result.final_response)


def test_command_follow_up_with_partial_values_stays_input_required() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="이름은 demo야 cpu는 1이야",
        session_context={
            "last_message_text": "프로젝트 하나 만들어줘",
            "last_request_status": "input_required",
            "last_request_type": "command",
        },
    )

    assert result.status == "input_required"
    assert result.requires_approval is False
    assert result.missing_inputs == ["max_memory", "max_disk"]


def test_command_follow_up_with_all_values_builds_user_facing_plan() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
        session_context={
            "last_message_text": "프로젝트 하나 만들어줘",
            "last_request_status": "input_required",
            "last_request_type": "command",
        },
    )

    assert result.status == "pending_approval"
    assert result.final_response is not None
    assert "프로젝트 이름 demo" in result.final_response
    assert "최대 CPU 1" in result.final_response
    assert "최대 메모리 0.5GB" in result.final_response
    assert "최대 디스크 10GB" in result.final_response


def test_command_follow_up_uses_last_effective_message_for_multi_turn_collection() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="메모리는 0.5야 디스크는 10이야",
        session_context={
            "last_message_text": "이름은 demo야 cpu는 1이야",
            "last_effective_message_text": "프로젝트 하나 만들어줘\n이름은 demo야 cpu는 1이야",
            "last_request_status": "input_required",
            "last_request_type": "command",
        },
    )

    assert result.status == "pending_approval"
    assert result.final_response is not None
    assert "프로젝트 이름 demo" in result.final_response
    assert "최대 CPU 1" in result.final_response
    assert "최대 메모리 0.5GB" in result.final_response
    assert "최대 디스크 10GB" in result.final_response


def test_application_create_without_required_business_values_returns_input_required() -> None:
    class ApplicationCreateRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="application.create_apps",
                    source_file="ai_registry/application.create_apps.ai.yaml",
                    operation_id="create_apps",
                    path="/apps",
                    method="POST",
                    summary="애플리케이션 생성",
                    capability="애플리케이션 생성",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("애플리케이션 생성",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("애플리케이션 생성",),
                    required_headers=(),
                    required_inputs={
                        "headers": [],
                        "path": [],
                        "query": [],
                        "body": {
                            "required": True,
                            "required_fields": ["name", "cpu", "memory", "disk", "project_id", "port"],
                        },
                    },
                    important_inputs={
                        "path": [],
                        "query": [],
                        "body": ["name", "cpu", "memory", "disk", "project_id", "port"],
                    },
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=ApplicationCreateRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트에 앱 만들어줘",
    )

    assert result.status == "input_required"
    assert result.missing_inputs == ["name", "cpu", "memory", "disk", "port"]
    assert result.final_response is not None
    assert "프로젝트 이름" not in result.final_response


def test_project_update_resource_without_required_business_values_returns_input_required() -> None:
    class ProjectResourceRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="project.update_resource",
                    source_file="ai_registry/project.update_resource.ai.yaml",
                    operation_id="update_project_resource",
                    path="/projects/{project_id}/resource",
                    method="PATCH",
                    summary="프로젝트 리소스 수정",
                    capability="프로젝트 리소스 수정",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("프로젝트 리소스 수정",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("프로젝트 리소스 수정",),
                    required_headers=("X-User-Id",),
                    required_inputs={
                        "headers": [],
                        "path": [{"name": "project_id", "required": True}],
                        "query": [],
                        "body": {"required": True, "required_fields": []},
                    },
                    important_inputs={
                        "path": ["project_id"],
                        "query": [],
                        "body": ["max_cpu", "max_memory", "max_disk"],
                    },
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=ProjectResourceRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 리소스 늘려줘",
    )

    assert result.status == "input_required"
    assert result.missing_inputs == ["max_cpu", "max_memory", "max_disk"]
    assert result.final_response is not None
    assert "최대 CPU" in result.final_response


def test_project_update_resource_with_required_business_values_returns_pending_approval() -> None:
    class ProjectResourceRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="project.update_resource",
                    source_file="ai_registry/project.update_resource.ai.yaml",
                    operation_id="update_project_resource",
                    path="/projects/{project_id}/resource",
                    method="PATCH",
                    summary="프로젝트 리소스 수정",
                    capability="프로젝트 리소스 수정",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("프로젝트 리소스 수정",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("프로젝트 리소스 수정",),
                    required_headers=("X-User-Id",),
                    required_inputs={
                        "headers": [],
                        "path": [{"name": "project_id", "required": True}],
                        "query": [],
                        "body": {"required": True, "required_fields": []},
                    },
                    important_inputs={
                        "path": ["project_id"],
                        "query": [],
                        "body": ["max_cpu", "max_memory", "max_disk"],
                    },
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=ProjectResourceRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 리소스 늘려줘 cpu는 2야 메모리는 1이야 디스크는 20이야",
    )

    assert result.status == "pending_approval"
    assert result.requires_approval is True
    assert result.final_response is not None
    assert "대상 프로젝트 demo" in result.final_response
    assert "최대 CPU 2" in result.final_response
    assert "최대 메모리 1GB" in result.final_response
    assert "최대 디스크 20GB" in result.final_response


def test_command_validation_failure_returns_input_required() -> None:
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FailingDownstreamDispatcher(),
        resolver_service=FakeResolverService(),
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

    assert result.status == "input_required"
    assert result.final_response == "요청값이 올바르지 않습니다."
    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "clarify"
    assert result.task_snapshot is not None
    assert result.task_snapshot["status"] == "input_required"


def test_project_update_without_target_name_requests_project_name_instead_of_id() -> None:
    class UpdateOnlyRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="project.update_name",
                    source_file="ai_registry/project.update_name.ai.yaml",
                    operation_id="update_project_name",
                    path="/projects/{project_id}/name",
                    method="PATCH",
                    summary="프로젝트 이름 수정",
                    capability="프로젝트 이름 수정",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("프로젝트 이름 수정",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("프로젝트 이름 수정",),
                    required_headers=("X-User-Id",),
                    required_inputs={
                        "headers": [],
                        "path": [{"name": "project_id", "required": True}],
                        "query": [],
                        "body": {"required": True, "required_fields": ["name"]},
                    },
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="수정 결과",
                    plan_template=("입력 확인",),
                    examples=(),
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=UpdateOnlyRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="프로젝트 이름 바꿔줘",
    )

    assert result.status == "input_required"
    assert result.missing_inputs == ["project_name", "name"]
    assert "대상 프로젝트" in str(result.final_response)


def test_command_plan_hides_internal_operation_id() -> None:
    class MultiCandidateRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="project.update_name",
                    source_file="ai_registry/project.update_name.ai.yaml",
                    operation_id="update_project_name",
                    path="/projects/{project_id}/name",
                    method="PATCH",
                    summary="프로젝트 이름 수정",
                    capability="프로젝트 이름 수정",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("프로젝트 이름 수정",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("프로젝트 이름 수정",),
                    required_headers=("X-User-Id",),
                    required_inputs={
                        "headers": [],
                        "path": [{"name": "project_id", "required": True}],
                        "query": [],
                        "body": {"required": True, "required_fields": ["name"]},
                    },
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="수정 결과",
                    plan_template=("입력 확인",),
                    examples=(),
                ),
                RegistryEntry(
                    id="project.update_resource",
                    source_file="ai_registry/project.update_resource.ai.yaml",
                    operation_id="update_project_resource",
                    path="/projects/{project_id}/resource",
                    method="PATCH",
                    summary="프로젝트 리소스 수정",
                    capability="프로젝트 리소스 수정",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("프로젝트 리소스 수정",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("프로젝트 리소스 수정",),
                    required_headers=("X-User-Id",),
                    required_inputs={
                        "headers": [],
                        "path": [{"name": "project_id", "required": True}],
                        "query": [],
                        "body": {"required": True, "required_fields": ["cpu"]},
                    },
                    preconditions=(),
                    missing_info_questions=(),
                    response_interpretation="수정 결과",
                    plan_template=("입력 확인",),
                    examples=(),
                ),
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=MultiCandidateRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 이름은 chatops-renamed로 바꿔줘",
    )

    assert result.status == "pending_approval"
    assert result.final_response is not None
    assert "실행할까요" in result.final_response
    assert "project.update_name" not in result.final_response
    assert "project.update_resource" not in result.final_response


def test_application_delete_without_target_values_returns_input_required() -> None:
    class ApplicationDeleteRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="application.delete_apps",
                    source_file="ai_registry/application.delete_apps.ai.yaml",
                    operation_id="delete_apps",
                    path="/apps",
                    method="DELETE",
                    summary="애플리케이션 삭제",
                    capability="애플리케이션 삭제",
                    usable_in=("command",),
                    operation_kind="delete",
                    when_to_use=("애플리케이션 삭제",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="high",
                    side_effects=("애플리케이션 삭제",),
                    required_headers=(),
                    required_inputs={"headers": [], "path": [], "query": [], "body": None},
                    important_inputs={"path": [], "query": [], "body": ["project_id", "application_id"]},
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=ApplicationDeleteRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="앱 삭제해줘",
    )

    assert result.status == "input_required"
    assert result.missing_inputs == ["project_name", "application_name"]
    assert "대상 프로젝트" in str(result.final_response)
    assert "앱 이름" in str(result.final_response)


def test_application_resource_update_plan_uses_user_friendly_labels() -> None:
    class ApplicationResourceRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="application.patch_apps_resources",
                    source_file="ai_registry/application.patch_apps_resources.ai.yaml",
                    operation_id="patch_apps_resources",
                    path="/apps/resources",
                    method="PATCH",
                    summary="애플리케이션 자원 변경",
                    capability="애플리케이션 자원 변경",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("애플리케이션 자원 변경",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("애플리케이션 자원 변경",),
                    required_headers=(),
                    required_inputs={"headers": [], "path": [], "query": [], "body": {"required": True, "required_fields": []}},
                    important_inputs={"path": [], "query": [], "body": ["project_id", "application_id", "max_cpu", "max_memory", "max_disk"]},
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=ApplicationResourceRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 api-demo 앱 리소스 변경해줘 cpu는 2야 메모리는 1024야 디스크는 12야",
    )

    assert result.status == "pending_approval"
    assert result.final_response is not None
    assert "애플리케이션 자원" in result.final_response
    assert "대상 프로젝트 demo" in result.final_response
    assert "앱 이름 api-demo" in result.final_response
    assert "최대 CPU 2" in result.final_response
    assert "최대 메모리 1024MB" in result.final_response
    assert "최대 디스크 12GB" in result.final_response


def test_application_github_update_without_github_values_returns_input_required() -> None:
    class ApplicationGithubRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="application.patch_apps_github",
                    source_file="ai_registry/application.patch_apps_github.ai.yaml",
                    operation_id="patch_apps_github",
                    path="/apps/github",
                    method="PATCH",
                    summary="애플리케이션 GitHub 연결",
                    capability="애플리케이션 GitHub 연결",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("애플리케이션 GitHub 연결",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("애플리케이션 GitHub 연결",),
                    required_headers=(),
                    required_inputs={
                        "headers": [],
                        "path": [],
                        "query": [],
                        "body": {"required": True, "required_fields": ["appDeploymentId", "owner", "repository"]},
                    },
                    important_inputs={
                        "path": [],
                        "query": [],
                        "body": ["project_id", "appDeploymentId", "owner", "repository", "branch"],
                    },
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=ApplicationGithubRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 api-demo 앱 깃허브 연결해줘",
    )

    assert result.status == "input_required"
    assert result.missing_inputs == ["owner", "repository", "branch"]
    assert "GitHub 소유자" in str(result.final_response)
    assert "저장소 이름" in str(result.final_response)
    assert "브랜치" in str(result.final_response)


def test_application_github_follow_up_uses_previous_effective_message() -> None:
    class ApplicationGithubRegistry(FakeRegistryService):
        def _command_entries(self) -> list[RegistryEntry]:
            return [
                RegistryEntry(
                    id="application.patch_apps_github",
                    source_file="ai_registry/application.patch_apps_github.ai.yaml",
                    operation_id="patch_apps_github",
                    path="/apps/github",
                    method="PATCH",
                    summary="애플리케이션 GitHub 연결",
                    capability="애플리케이션 GitHub 연결",
                    usable_in=("command",),
                    operation_kind="write",
                    when_to_use=("애플리케이션 GitHub 연결",),
                    when_not_to_use=(),
                    requires_confirmation=True,
                    risk_level="medium",
                    side_effects=("애플리케이션 GitHub 연결",),
                    required_headers=(),
                    required_inputs={
                        "headers": [],
                        "path": [],
                        "query": [],
                        "body": {"required": True, "required_fields": ["appDeploymentId", "owner", "repository"]},
                    },
                    important_inputs={
                        "path": [],
                        "query": [],
                        "body": ["project_id", "appDeploymentId", "owner", "repository", "branch"],
                    },
                )
            ]

    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=ApplicationGithubRegistry(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    first = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="demo 프로젝트 api-demo 앱 깃허브 연결해줘",
    )
    second = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="owner는 M-ADP야 repository는 chatops야 branch는 main이야",
        session_context={
            "last_request_status": first.status,
            "last_message_text": "demo 프로젝트 api-demo 앱 깃허브 연결해줘",
            "last_effective_message_text": first.effective_message_text,
        },
    )

    assert second.status == "pending_approval"
    assert second.final_response is not None
    assert "대상 프로젝트 demo" in second.final_response
    assert "앱 이름 api-demo" in second.final_response
    assert "GitHub 소유자 M-ADP" in second.final_response


def test_correction_during_pending_approval_replans_with_new_values() -> None:
    """pending_approval 상태에서 '아니 CPU는 2로 해줘'로 정정하면 새 값으로 re-plan된다."""
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    first = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
        session_context={
            "last_message_text": "프로젝트 하나 만들어줘",
            "last_request_status": "input_required",
            "last_request_type": "command",
        },
    )
    assert first.status == "pending_approval"

    # 정정: CPU를 2로 변경
    second = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="아니 cpu는 2로 바꿔줘",
        session_context={
            "last_message_text": "이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
            "last_effective_message_text": first.effective_message_text,
            "last_request_status": "pending_approval",
            "last_request_type": "command",
        },
    )

    assert second.status == "pending_approval"
    assert second.final_response is not None
    assert "최대 CPU 2" in second.final_response
    assert "최대 메모리 0.5GB" in second.final_response
    assert "프로젝트 이름 demo" in second.final_response


def test_correction_memory_value_during_pending_approval() -> None:
    """pending_approval에서 '메모리는 1기가로 해줘'로 정정하면 메모리 값이 변경된다."""
    graph_service = GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        adapter_service=FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    first = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
        session_context={
            "last_message_text": "프로젝트 하나 만들어줘",
            "last_request_status": "input_required",
            "last_request_type": "command",
        },
    )
    assert first.status == "pending_approval"

    second = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="근데 메모리는 1로 변경해줘",
        session_context={
            "last_message_text": "이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
            "last_effective_message_text": first.effective_message_text,
            "last_request_status": "pending_approval",
            "last_request_type": "command",
        },
    )

    assert second.status == "pending_approval"
    assert second.final_response is not None
    assert "최대 메모리 1GB" in second.final_response
