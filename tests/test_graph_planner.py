from __future__ import annotations

from dataclasses import dataclass

from chatops.graph.planner_service import PlannerService
from chatops.services.registry import RegistryEntry, ScoredCandidate


@dataclass
class FakeLLMService:
    def build_plan_object(
        self,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, object]:
        del candidate_operation_ids
        return {
            "goal": message_text,
            "specialist": "application",
            "entities": {"project_name": "demo", "application_name": "api"},
            "constraints": {"approval_required": request_type == "command"},
            "candidate_steps": [
                {
                    "step_id": "create-app",
                    "title": "앱 생성",
                    "status": "planned",
                    "operation_id": "application.create_apps",
                }
            ],
            "risk_level": "medium",
            "required_clarifications": ["cpu", "memory", "disk"],
        }


@dataclass
class FakeRegistryService:
    def find_scored_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[ScoredCandidate]:
        del user_text, limit
        operation_id = "application.create_apps" if usable_in == "command" else "monitoring.get_app_deployment_traffic"
        entry = RegistryEntry(
            id=operation_id,
            source_file=f"ai_registry/{operation_id}.ai.yaml",
            operation_id=operation_id.split(".")[-1],
            path="/dummy",
            method="POST" if usable_in == "command" else "GET",
            summary="dummy",
            capability="dummy",
            usable_in=(usable_in,),
            operation_kind="write" if usable_in == "command" else "read",
            when_to_use=(),
            when_not_to_use=(),
            requires_confirmation=usable_in == "command",
            risk_level="medium" if usable_in == "command" else "low",
            side_effects=(),
            required_headers=("X-User-Id",),
            required_inputs={},
            preconditions=(),
            missing_info_questions=(),
            response_interpretation="dummy",
            plan_template=(),
            examples=(),
        )
        return [ScoredCandidate(entry=entry, score=100)]


def test_planner_service_builds_structured_plan_object_for_command() -> None:
    planner = PlannerService(
        llm_service=FakeLLMService(),
        registry_service=FakeRegistryService(),
    )

    plan = planner.build(
        message_text="demo 프로젝트에 api 앱 만들어줘",
        request_type="command",
    )

    assert plan["specialist"] == "application"
    assert plan["candidate_steps"][0]["operation_id"] == "application.create_apps"
    assert plan["constraints"]["approval_required"] is True
    assert plan["required_clarifications"] == ["cpu", "memory", "disk"]
