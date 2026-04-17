from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chatops.evaluation.harness import ScenarioRunner, load_quality_scenarios
from chatops.graph.service import GraphService
from chatops.services.registry import RegistryEntry, ScoredCandidate
from chatops.services.resolver import ParameterResolverService
from tests.test_graph_service import FakeLLMService


def _entry(
    entry_id: str,
    *,
    usable_in: tuple[str, ...],
    operation_kind: str,
    path: str,
    required_inputs: dict,
    important_inputs: dict | None = None,
    risk_level: str = "low",
    requires_confirmation: bool = False,
    capability: str | None = None,
) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path=path,
        method="GET" if operation_kind == "read" else "POST",
        summary=entry_id,
        capability=capability or entry_id,
        usable_in=usable_in,
        operation_kind=operation_kind,
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=requires_confirmation,
        risk_level=risk_level,
        side_effects=(),
        required_headers=("X-User-Id",),
        required_inputs=required_inputs,
        important_inputs=important_inputs or {},
    )


QUERY_ENTRIES = {
    "project.list_projects": _entry(
        "project.list_projects",
        usable_in=("query",),
        operation_kind="read",
        path="/projects",
        capability="프로젝트 목록 조회",
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
    ),
    "project.get": _entry(
        "project.get",
        usable_in=("query",),
        operation_kind="read",
        path="/projects/{project_id}",
        capability="프로젝트 상세 조회",
        required_inputs={"headers": [], "path": [{"name": "project_id", "required": True}], "query": [], "body": None},
    ),
    "project.list_members": _entry(
        "project.list_members",
        usable_in=("query",),
        operation_kind="read",
        path="/projects/{project_id}/members",
        capability="프로젝트 멤버 조회",
        required_inputs={"headers": [], "path": [{"name": "project_id", "required": True}], "query": [], "body": None},
    ),
    "project.check_owner": _entry(
        "project.check_owner",
        usable_in=("query",),
        operation_kind="read",
        path="/projects/{project_id}/owner",
        capability="프로젝트 소유자 확인",
        required_inputs={"headers": [], "path": [{"name": "project_id", "required": True}], "query": [], "body": None},
    ),
    "application.get_apps": _entry(
        "application.get_apps",
        usable_in=("query",),
        operation_kind="read",
        path="/apps",
        capability="앱 목록 조회",
        required_inputs={"headers": [], "path": [], "query": [{"name": "project_id", "required": True}], "body": None},
    ),
    "application.get_apps_status": _entry(
        "application.get_apps_status",
        usable_in=("query",),
        operation_kind="read",
        path="/apps/status",
        capability="앱 상태 조회",
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={"path": [{"name": "project_id"}, {"name": "application_id"}], "query": [], "body": []},
    ),
    "application.get_apps_logs": _entry(
        "application.get_apps_logs",
        usable_in=("query",),
        operation_kind="read",
        path="/apps/logs",
        capability="앱 로그 조회",
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={"path": [{"name": "project_id"}, {"name": "app_deployment_name"}], "query": [], "body": []},
    ),
    "application.get_apps_details": _entry(
        "application.get_apps_details",
        usable_in=("query",),
        operation_kind="read",
        path="/apps/details",
        capability="앱 상세 조회",
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={"path": [{"name": "project_id"}, {"name": "app_deployment_name"}], "query": [], "body": []},
    ),
    "monitoring.get_app_deployment_traffic": _entry(
        "monitoring.get_app_deployment_traffic",
        usable_in=("query",),
        operation_kind="read",
        path="/monitoring/app-deployment/{project_id}/{app_deployment_name}",
        capability="앱 트래픽 조회",
        required_inputs={
            "headers": [],
            "path": [
                {"name": "project_id", "required": True},
                {"name": "app_deployment_name", "required": True},
            ],
            "query": [],
            "body": None,
        },
    ),
}

COMMAND_ENTRIES = {
    "project.create": _entry(
        "project.create",
        usable_in=("command",),
        operation_kind="write",
        path="/projects",
        capability="프로젝트 생성",
        requires_confirmation=True,
        risk_level="medium",
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["name"]},
        },
        important_inputs={"path": [], "query": [], "body": ["name", "max_cpu", "max_memory", "max_disk"]},
    ),
    "project.update_name": _entry(
        "project.update_name",
        usable_in=("command",),
        operation_kind="write",
        path="/projects/{project_id}/name",
        capability="프로젝트 이름 변경",
        requires_confirmation=True,
        risk_level="medium",
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {"required": True, "required_fields": ["name"]},
        },
    ),
    "project.delete": _entry(
        "project.delete",
        usable_in=("command",),
        operation_kind="delete",
        path="/projects/{project_id}",
        capability="프로젝트 삭제",
        requires_confirmation=True,
        risk_level="high",
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": None,
        },
    ),
    "project.add_member": _entry(
        "project.add_member",
        usable_in=("command",),
        operation_kind="write",
        path="/projects/{project_id}/members",
        capability="프로젝트 멤버 추가",
        requires_confirmation=True,
        risk_level="medium",
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {"required": True, "required_fields": ["target_user_id"]},
        },
    ),
    "project.remove_member": _entry(
        "project.remove_member",
        usable_in=("command",),
        operation_kind="delete",
        path="/projects/{project_id}/members/{target_user_id}",
        capability="프로젝트 멤버 제거",
        requires_confirmation=True,
        risk_level="high",
        required_inputs={
            "headers": [],
            "path": [
                {"name": "project_id", "required": True},
                {"name": "target_user_id", "required": True},
            ],
            "query": [],
            "body": None,
        },
    ),
    "project.transfer_ownership": _entry(
        "project.transfer_ownership",
        usable_in=("command",),
        operation_kind="write",
        path="/projects/{project_id}/owner",
        capability="프로젝트 소유권 이전",
        requires_confirmation=True,
        risk_level="high",
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {"required": True, "required_fields": ["target_user_id"]},
        },
    ),
    "application.create_apps": _entry(
        "application.create_apps",
        usable_in=("command",),
        operation_kind="write",
        path="/apps",
        capability="앱 생성",
        requires_confirmation=True,
        risk_level="medium",
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["name", "cpu", "memory", "disk", "project_id"]},
        },
    ),
    "application.patch_apps_github": _entry(
        "application.patch_apps_github",
        usable_in=("command",),
        operation_kind="write",
        path="/apps/github",
        capability="앱 GitHub 연결 변경",
        requires_confirmation=True,
        risk_level="medium",
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["appDeploymentId", "owner", "repository", "branch"]},
        },
    ),
    "application.delete_apps": _entry(
        "application.delete_apps",
        usable_in=("command",),
        operation_kind="delete",
        path="/apps",
        capability="앱 삭제",
        requires_confirmation=True,
        risk_level="high",
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["appDeploymentId"]},
        },
    ),
    "application.patch_apps_resources": _entry(
        "application.patch_apps_resources",
        usable_in=("command",),
        operation_kind="write",
        path="/apps/resources",
        capability="앱 리소스 변경",
        requires_confirmation=True,
        risk_level="medium",
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["appDeploymentId"]},
        },
        important_inputs={"path": [], "query": [], "body": ["cpu"]},
    ),
}

ENTRIES = {**QUERY_ENTRIES, **COMMAND_ENTRIES}


class QualityRegistry:
    def find_scored_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[ScoredCandidate]:
        del limit
        text = user_text.lower()
        if "백업" in text:
            return []

        if usable_in == "query":
            if "demo 상태" in user_text:
                return [
                    ScoredCandidate(entry=QUERY_ENTRIES["project.get"], score=100),
                    ScoredCandidate(entry=QUERY_ENTRIES["application.get_apps_status"], score=99),
                ]
            if "트래픽" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["monitoring.get_app_deployment_traffic"], score=100)]
            if "owner" in text or "소유자" in user_text or "여부" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["project.check_owner"], score=100)]
            if "멤버 목록" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["project.list_members"], score=100)]
            if "앱 목록" in user_text or "앱 리스트" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["application.get_apps"], score=100)]
            if "로그" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["application.get_apps_logs"], score=100)]
            if ("상세" in user_text or "정보" in user_text) and "앱" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["application.get_apps_details"], score=100)]
            if "앱 상태" in user_text or "리소스 사용량" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["application.get_apps_status"], score=100)]
            if "프로젝트 목록" in user_text:
                return [ScoredCandidate(entry=QUERY_ENTRIES["project.list_projects"], score=100)]
            if "프로젝트" in user_text and any(marker in user_text for marker in ("자세히", "상태", "상세")):
                return [ScoredCandidate(entry=QUERY_ENTRIES["project.get"], score=100)]
            return []

        if "멤버 제거" in user_text:
            return [ScoredCandidate(entry=COMMAND_ENTRIES["project.remove_member"], score=100)]
        if "멤버 추가" in user_text:
            return [ScoredCandidate(entry=COMMAND_ENTRIES["project.add_member"], score=100)]
        if "소유권" in user_text:
            return [ScoredCandidate(entry=COMMAND_ENTRIES["project.transfer_ownership"], score=100)]
        if "이름을" in user_text and "바꿔" in user_text:
            return [ScoredCandidate(entry=COMMAND_ENTRIES["project.update_name"], score=100)]
        if "프로젝트" in user_text and "삭제" in user_text:
            return [ScoredCandidate(entry=COMMAND_ENTRIES["project.delete"], score=100)]
        if "github" in text:
            return [ScoredCandidate(entry=COMMAND_ENTRIES["application.patch_apps_github"], score=100)]
        if "앱" in user_text and "삭제" in user_text:
            return [ScoredCandidate(entry=COMMAND_ENTRIES["application.delete_apps"], score=100)]
        if "앱" in user_text and any(marker in user_text for marker in ("늘려", "리소스", "cpu")):
            return [ScoredCandidate(entry=COMMAND_ENTRIES["application.patch_apps_resources"], score=100)]
        if "앱" in user_text and any(marker in user_text for marker in ("만들어", "생성")):
            return [ScoredCandidate(entry=COMMAND_ENTRIES["application.create_apps"], score=100)]
        if any(marker in user_text for marker in ("프로젝트", "만들어", "생성")):
            return [ScoredCandidate(entry=COMMAND_ENTRIES["project.create"], score=100)]
        return []

    def detect_ambiguity(self, scored_candidates: list[ScoredCandidate]) -> tuple[bool, list[ScoredCandidate]]:
        if len(scored_candidates) >= 2:
            first = scored_candidates[0].entry.id.split(".")[0]
            second = scored_candidates[1].entry.id.split(".")[0]
            if first != second:
                return True, scored_candidates[:2]
        return False, []

    def get_entry(self, entry_id: str):
        return ENTRIES.get(entry_id)

    def all_enabled_entries(self) -> list:
        return list(ENTRIES.values())


@dataclass
class QualityDispatcher:
    calls: list[str] = field(default_factory=list)
    executed_operation_ids: list[str] = field(default_factory=list)

    async def execute_query(self, operation, user_id: str, user_role=None, org_id=None, resolved_inputs=None):
        del user_id, user_role, org_id, resolved_inputs
        self.calls.append(operation.id)
        self.executed_operation_ids.append(operation.id)
        return {"summary": f"{operation.id} ok"}

    async def execute_command(self, operation, user_id: str, user_role=None, org_id=None, resolved_inputs=None):
        del user_id, user_role, org_id, resolved_inputs
        self.calls.append(operation.id)
        self.executed_operation_ids.append(operation.id)
        return {"success": True, "summary": f"{operation.id} ok", "result": {}}


class GroundedFakeLLMService(FakeLLMService):
    def classify(self, message_text: str) -> dict[str, object]:
        if "여부" in message_text or ("확인" in message_text and "프로젝트" in message_text):
            return {
                "request_type": "query",
                "intent": "query_status",
                "classification_reason": "확인형 조회 요청",
                "classification_confidence": 0.94,
            }
        return super().classify(message_text)

    def answer_inquiry(
        self,
        message_text: str,
        supported_operations: list[dict[str, object]] | None = None,
    ) -> str:
        if supported_operations == []:
            return "현재 지원하지 않는 기능입니다. 지원되는 프로젝트, 앱, 모니터링 조회 및 변경 작업만 요청할 수 있습니다."
        return super().answer_inquiry(message_text)

    def converse_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tool_specs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from tests.test_graph_service import _text_response, _tool_use_response

        # Extract first user message text (for vague pattern detection)
        text = ""
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and "text" in block:
                            text = str(block["text"])
                            break
                elif isinstance(content, str):
                    text = content
                break
            elif hasattr(msg, "type") and msg.type == "human":
                content = msg.content
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and "text" in block:
                            text = str(block["text"])
                            break
                break

        # Check if last message is tool_result → return summary
        last = messages[-1] if messages else None
        if last is not None:
            last_content = last.get("content", []) if isinstance(last, dict) else getattr(last, "content", [])
            if not isinstance(last_content, list):
                last_content = []
            for block in last_content:
                if isinstance(block, dict) and "toolResult" in block:
                    result_content = block["toolResult"].get("content", [])
                    summary = ""
                    for c in result_content:
                        if isinstance(c, dict) and "json" in c:
                            json_result = c["json"]
                            summary = json_result.get("summary", str(json_result))
                    return {
                        "stop_reason": "end_turn",
                        "assistant_message": {"role": "assistant", "content": [{"text": f"조회 응답: {summary}"}]},
                        "tool_calls": [],
                        "text_content": f"조회 응답: {summary}",
                    }

        # Vague messages without specific identifiers → ask for clarification (dispatched=False)
        # Only match when the message is EXACTLY the vague pattern (no project/app qualifiers)
        stripped = text.strip()
        vague_patterns = ["앱 상태 보여줘", "demo 상태 보여줘"]
        if any(stripped == p for p in vague_patterns):
            return {
                "stop_reason": "end_turn",
                "assistant_message": {"role": "assistant", "content": [{"text": "어느 프로젝트의 어떤 앱인지 알려주세요."}]},
                "tool_calls": [],
                "text_content": "어느 프로젝트의 어떤 앱인지 알려주세요.",
            }

        # Inquiry: "방법", "알려줘", "설명", "백업"
        if any(kw in text for kw in ("방법", "알려줘", "설명")):
            return {
                "stop_reason": "end_turn",
                "assistant_message": {"role": "assistant", "content": [{"text": f"문의 응답: {text}"}]},
                "tool_calls": [],
                "text_content": f"문의 응답: {text}",
            }

        # Missing required values for command → return clarification text (dispatched=False)
        # "프로젝트 하나 만들어줘" without complete parameters
        if "만들어줘" in text and not any(kw in text for kw in ("name=", "이름은", "cpu", "memory", "disk", "max_cpu")):
            return {
                "stop_reason": "end_turn",
                "assistant_message": {"role": "assistant", "content": [{"text": "프로젝트 이름, CPU, 메모리, 디스크 정보를 알려주세요."}]},
                "tool_calls": [],
                "text_content": "프로젝트 이름, CPU, 메모리, 디스크 정보를 알려주세요.",
            }

        # Fall back to parent for all other cases
        return super().converse_with_tools(messages, system_prompt, tool_specs)


def test_quality_baseline_suite_scores_at_least_80() -> None:
    dispatcher = QualityDispatcher()
    graph_service = GraphService(
        llm_service=GroundedFakeLLMService(),
        registry_service=QualityRegistry(),
        downstream_dispatcher=dispatcher,
        resolver_service=ParameterResolverService(),
    )
    runner = ScenarioRunner(
        graph_service=graph_service,
        dispatch_count_getter=lambda: len(dispatcher.executed_operation_ids),
    )

    report = runner.run(load_quality_scenarios())

    assert report.total_cases >= 30
    assert report.passed_cases == report.total_cases
    assert report.overall_score >= 80
