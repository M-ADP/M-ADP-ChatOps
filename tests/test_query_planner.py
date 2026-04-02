from __future__ import annotations

from dataclasses import dataclass

from chatops.domain.enums import RequestStatus
from chatops.graph.query_planner import QueryPlanningService
from chatops.graph.state import GraphState
from chatops.services.registry import RegistryEntry, ScoredCandidate


@dataclass
class _Registry:
    scored: list[ScoredCandidate]
    ambiguous: tuple[bool, list[ScoredCandidate]] = (False, ())

    def find_scored_candidates(self, user_text: str, usable_in: str):
        del user_text, usable_in
        return self.scored

    def detect_ambiguity(self, scored_candidates):
        del scored_candidates
        return self.ambiguous


@dataclass
class _Resolver:
    resolved_inputs: dict[str, object]

    def resolve(self, operation, message_text: str, session_context=None):
        del operation, message_text, session_context
        return dict(self.resolved_inputs)


def _entry(entry_id: str) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path="/test",
        method="GET",
        summary=entry_id,
        capability=entry_id,
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=(),
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={},
    )


def _state(message_text: str) -> GraphState:
    return {
        "request_id": 1,
        "session_id": 1,
        "user_id": "u1",
        "message_text": message_text,
        "effective_message_text": message_text,
        "selected_operation_ids": [],
    }


def test_query_planner_returns_ambiguity_without_execution() -> None:
    first = ScoredCandidate(entry=_entry("project.get"), score=10)
    second = ScoredCandidate(entry=_entry("application.get_apps_status"), score=9)
    planner = QueryPlanningService(
        registry_service=_Registry(scored=[first, second], ambiguous=(True, [first, second])),
        resolver_service=_Resolver({}),
        auth_precheck_failure=lambda operation, state, operation_ids: None,
        missing_required_inputs=lambda operation, resolved_inputs: [],
        ambiguity_question_builder=lambda candidates: "프로젝트 상태인가요, 앱 상태인가요?",
        missing_input_response_builder=lambda operation_id, missing_inputs: "",
    )

    result = planner.prepare(_state("demo 상태 보여줘"))

    assert result["request_status"] == RequestStatus.AMBIGUOUS.value
    assert result["final_response"] == "프로젝트 상태인가요, 앱 상태인가요?"


def test_query_planner_returns_input_required_before_dispatch() -> None:
    planner = QueryPlanningService(
        registry_service=_Registry(scored=[ScoredCandidate(entry=_entry("application.get_apps_status"), score=10)]),
        resolver_service=_Resolver({"references": {}}),
        auth_precheck_failure=lambda operation, state, operation_ids: None,
        missing_required_inputs=lambda operation, resolved_inputs: ["project_name", "application_name"],
        ambiguity_question_builder=lambda candidates: "",
        missing_input_response_builder=lambda operation_id, missing_inputs: "어느 프로젝트의 어떤 앱인지 알려주세요.",
    )

    result = planner.prepare(_state("앱 상태 보여줘"))

    assert result["request_status"] == RequestStatus.INPUT_REQUIRED.value
    assert result["missing_inputs"] == ["project_name", "application_name"]
    assert result["final_response"] == "어느 프로젝트의 어떤 앱인지 알려주세요."

