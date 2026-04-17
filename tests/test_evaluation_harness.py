from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from chatops.evaluation.harness import ScenarioCase, ScenarioExpectation, ScenarioRunner
from chatops.graph.service import GraphService
from chatops.services.resolver import ParameterResolverService
from chatops.services.registry import RegistryEntry, ScoredCandidate
from tests.test_graph_service import FakeLLMService, FakeRegistryService


@dataclass
class RecordingDispatcher:
    calls: list[str] = field(default_factory=list)

    async def execute_query(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del user_id, user_role, org_id, resolved_inputs
        self.calls.append(operation.id)
        return {"summary": f"{operation.id} ok"}

    async def execute_command(
        self,
        operation,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del user_id, user_role, org_id, resolved_inputs
        self.calls.append(operation.id)
        return {"success": True, "summary": f"{operation.id} ok", "result": {}}


class ScenarioRegistry(FakeRegistryService):
    def _query_entries(self) -> list[RegistryEntry]:
        return [
            RegistryEntry(
                id="monitoring.get_app_deployment_traffic",
                source_file="ai_registry/monitoring.get_app_deployment_traffic.ai.yaml",
                operation_id="get_app_deployment_traffic",
                path="/monitoring/app-deployment/{project_id}/{app_deployment_name}",
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
                required_inputs={
                    "headers": [],
                    "path": [
                        {"name": "project_id", "required": True},
                        {"name": "app_deployment_name", "required": True},
                    ],
                    "query": [],
                    "body": None,
                },
                important_inputs={},
                preconditions=(),
                missing_info_questions=(),
                response_interpretation="트래픽 요약",
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
                when_to_use=("앱 상태 조회",),
                when_not_to_use=(),
                requires_confirmation=False,
                risk_level="low",
                side_effects=(),
                required_headers=("X-User-Id",),
                required_inputs={"headers": [], "path": [], "query": [], "body": None},
                important_inputs={"path": [{"name": "project_id"}, {"name": "application_id"}], "query": [], "body": []},
                preconditions=(),
                missing_info_questions=(),
                response_interpretation="앱 상태",
                plan_template=(),
                examples=(),
            ),
        ]

    def find_scored_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[ScoredCandidate]:
        entries = self._query_entries() if usable_in == "query" else self._command_entries()
        if usable_in == "query" and "앱 상태" in user_text:
            ordered = [entry for entry in entries if entry.id == "application.get_apps_status"]
        else:
            ordered = [entries[0]]
        return [ScoredCandidate(entry=entry, score=100 - index) for index, entry in enumerate(ordered[:limit])]


def test_scenario_runner_scores_graph_cases_objectively() -> None:
    from tests.test_agent_loop import (
        FakeAgentLLMService,
        FakeAgentRegistryService,
        FakeAgentDownstreamDispatcher,
        FakeAgentResolverService,
        _QUERY_ENTRY,
        _text_response,
        _tool_use_response,
    )

    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "조회 응답: 트래픽 정상", "success": True},
    )
    llm = FakeAgentLLMService(responses=[
        _tool_use_response("monitoring__get_app_deployment_traffic", {
            "project_name": "demo",
            "application_name": "api-server",
        }),
        _text_response("조회 응답: 트래픽 정상"),
        _text_response("어느 프로젝트의 어떤 앱인지 알려주세요."),
    ])
    registry = FakeAgentRegistryService(entries=[_QUERY_ENTRY])
    graph_service = GraphService(
        llm_service=llm,
        registry_service=registry,
        downstream_dispatcher=dispatcher,
        resolver_service=FakeAgentResolverService(),
    )
    runner = ScenarioRunner(
        graph_service=graph_service,
        dispatch_count_getter=lambda: len(dispatcher.executed_operation_ids),
    )

    report = runner.run([
        ScenarioCase(
            name="query success",
            message_text="demo 프로젝트 api-server 앱 트래픽 상태 알려줘",
            session_id=9001,
            expectation=ScenarioExpectation(
                status="completed",
                request_type="agent",
                dispatched=True,
                response_contains=("조회 응답",),
            ),
        ),
        ScenarioCase(
            name="query clarification",
            message_text="앱 상태 보여줘",
            session_id=9002,
            expectation=ScenarioExpectation(
                status="completed",
                request_type="agent",
                dispatched=False,
            ),
        ),
    ])

    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.overall_score == 100
    assert report.metric_scores["status_accuracy"] == 100
    assert report.metric_scores["safety_behavior"] == 100


def test_scenario_runner_supports_extended_audit_assertions() -> None:
    class StubGraphService:
        def handle_request(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                status="pending_approval",
                request_type="command",
                error_code=None,
                missing_inputs=None,
                selected_operation_ids=["project.remove_member"],
                resolved_references={"project_name": "demo", "target_nickname": "alice"},
                final_response='{"operation": "project.remove_member", "project_name": "demo", "target_user": "alice"}',
                requires_approval=True,
                is_ambiguous=False,
            )

    report = ScenarioRunner(
        graph_service=StubGraphService(),
        dispatch_count_getter=lambda: 0,
        metadata_getter=lambda result: {"fallback_used": False, "permission_denied": False},
    ).run(
        [
            ScenarioCase(
                name="high risk approval",
                message_text="demo 프로젝트에서 alice 멤버 제거해줘",
                expectation=ScenarioExpectation(
                    status="pending_approval",
                    request_type="command",
                    requires_approval=True,
                    is_ambiguous=False,
                    clarification_contains=('"target_user": "alice"',),
                    fallback_used=False,
                    permission_denied=False,
                    dispatched=False,
                ),
            )
        ]
    )

    assert report.passed_cases == 1
    assert report.metric_scores["clarification_behavior"] == 100
    assert report.metric_scores["safety_behavior"] == 100
