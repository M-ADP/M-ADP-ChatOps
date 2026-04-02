from __future__ import annotations

from dataclasses import dataclass

from chatops.domain.enums import RequestStatus
from chatops.graph.command_planner import CommandPlanningService
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


@dataclass
class _PrecheckService:
    result: dict[str, object]

    def run(self, operation, resolved_inputs, user_id: str, user_role: str | None):
        del operation, resolved_inputs, user_id, user_role
        return dict(self.result)


def _entry(entry_id: str, *, risk_level: str = "medium") -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path="/test",
        method="POST",
        summary=entry_id,
        capability=entry_id,
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level=risk_level,
        side_effects=(),
        required_headers=(),
        required_inputs={"headers": [], "path": [], "query": [], "body": {"required": True, "required_fields": []}},
        important_inputs={},
    )


def _state(message_text: str) -> GraphState:
    return {
        "request_id": 1,
        "session_id": 1,
        "user_id": "u1",
        "user_role": "MEMBER",
        "message_text": message_text,
        "effective_message_text": message_text,
        "selected_operation_ids": [],
    }


def test_command_planner_returns_pending_approval_for_complete_medium_risk_command() -> None:
    operation = _entry("project.update_name", risk_level="medium")
    planner = CommandPlanningService(
        registry_service=_Registry(scored=[ScoredCandidate(entry=operation, score=10)]),
        resolver_service=_Resolver(
            {"references": {"project_name": "demo"}, "body": {"name": "renamed"}}
        ),
        auth_precheck_failure=lambda operation, state, operation_ids: None,
        missing_required_inputs=lambda operation, resolved_inputs: [],
        ambiguity_response_builder=lambda candidates: "모호합니다.",
        missing_input_response_builder=lambda operation, missing_inputs: "입력이 부족합니다.",
        precheck_service=_PrecheckService({"error": None, "resolved_ids": {"project_id": 42}}),
        risk_aware_plan_builder=lambda operation, resolved_inputs: "대상 프로젝트 demo, 새 이름 renamed 기준으로 프로젝트 이름을 변경할게요. 실행할까요?",
    )

    result = planner.prepare(_state("demo 프로젝트 이름을 renamed로 바꿔줘"))

    assert result["request_status"] == RequestStatus.PENDING_APPROVAL.value
    assert result["requires_approval"] is True
    assert result["risk_level"] == "medium"
    assert result["resolved_inputs"]["resolved_ids"] == {"project_id": 42}
    assert result["final_response"] == "대상 프로젝트 demo, 새 이름 renamed 기준으로 프로젝트 이름을 변경할게요. 실행할까요?"
