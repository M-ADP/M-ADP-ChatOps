from __future__ import annotations

import json
from pathlib import Path

from chatops.evaluation.harness import ScenarioCase, ScenarioExpectation, ScenarioRunner
from chatops.graph.service import GraphService
from chatops.services.resolver import ParameterResolverService
from tests.test_graph_service import (
    FakeDownstreamDispatcher,
    FakeLLMService,
    FakeRegistryService,
)


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "q1_golden_scenarios.json"


def _load_cases() -> list[ScenarioCase]:
    raw_cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases: list[ScenarioCase] = []
    for index, item in enumerate(raw_cases):
        expectation = item["expectation"]
        cases.append(
            ScenarioCase(
                name=item["name"],
                message_text=item["message_text"],
                # Use unique session IDs per case to prevent state accumulation
                session_id=item.get("session_id", 8000 + index),
                expectation=ScenarioExpectation(
                    status=expectation.get("status"),
                    request_type=expectation.get("request_type"),
                    requires_approval=expectation.get("requires_approval"),
                    selected_operation_ids=tuple(expectation.get("selected_operation_ids", [])),
                    response_contains=tuple(expectation.get("response_contains", [])),
                    dispatched=expectation.get("dispatched"),
                ),
            )
        )
    return cases


def _build_graph_service(dispatcher=None) -> GraphService:
    return GraphService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
        downstream_dispatcher=dispatcher or FakeDownstreamDispatcher(),
        resolver_service=ParameterResolverService(),
    )


def test_q1_agent_runtime_golden_scenarios_score_cleanly() -> None:
    from tests.test_agent_loop import FakeAgentDownstreamDispatcher

    dispatcher = FakeAgentDownstreamDispatcher(
        execute_result={"summary": "조회 응답: monitoring.get_app_deployment_traffic ok", "success": True},
    )
    runner = ScenarioRunner(
        graph_service=_build_graph_service(dispatcher),
        dispatch_count_getter=lambda: len(dispatcher.executed_operation_ids),
    )

    report = runner.run(_load_cases())

    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.overall_score == 100


def test_q1_agent_runtime_resume_flow_completes() -> None:
    graph_service = _build_graph_service()

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
    assert result.final_response is not None
