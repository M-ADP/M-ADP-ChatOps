from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlannerService:
    llm_service: Any
    registry_service: Any

    def build(self, *, message_text: str, request_type: str) -> dict[str, object] | None:
        if request_type not in {"query", "command"}:
            return None
        candidate_operation_ids = self._registry_candidate_operation_ids(
            message_text=message_text,
            request_type=request_type,
        )
        if hasattr(self.llm_service, "build_plan_object"):
            plan = self.llm_service.build_plan_object(
                message_text=message_text,
                request_type=request_type,
                candidate_operation_ids=candidate_operation_ids,
            )
            if isinstance(plan, dict):
                return plan
        return self._fallback_plan(
            message_text=message_text,
            request_type=request_type,
            candidate_operation_ids=candidate_operation_ids,
        )

    def _registry_candidate_operation_ids(
        self,
        *,
        message_text: str,
        request_type: str,
    ) -> list[str]:
        """registry 스코어링으로 후보를 뽑고, 결과 없으면 heuristic fallback."""
        if hasattr(self.registry_service, "find_scored_candidates"):
            scored = self.registry_service.find_scored_candidates(
                message_text, usable_in=request_type, limit=3,
            )
            if scored:
                return [sc.entry.id for sc in scored]
        return self._heuristic_candidate_operation_ids(
            message_text=message_text,
            request_type=request_type,
        )

    @staticmethod
    def _fallback_plan(
        *,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, object]:
        operation_id = candidate_operation_ids[0] if candidate_operation_ids else f"{request_type}.unknown"
        specialist = operation_id.split(".", 1)[0]
        return {
            "goal": message_text,
            "specialist": specialist,
            "entities": {},
            "constraints": {"approval_required": request_type == "command"},
            "candidate_steps": [
                {
                    "step_id": "primary-operation",
                    "title": "주요 작업 실행",
                    "status": "planned",
                    "operation_id": operation_id,
                }
            ],
            "risk_level": "medium" if request_type == "command" else "low",
            "required_clarifications": [],
        }

    @staticmethod
    def _heuristic_candidate_operation_ids(
        *,
        message_text: str,
        request_type: str,
    ) -> list[str]:
        normalized = message_text.lower()
        if request_type == "query":
            if "트래픽" in normalized:
                return ["monitoring.get_app_deployment_traffic"]
            if "상태" in normalized:
                return ["application.get_apps_status"]
            if "목록" in normalized:
                return ["project.list_projects"]
            return ["project.get"]
        if "앱" in normalized or "api" in normalized:
            return ["application.create_apps"]
        if "삭제" in normalized:
            return ["project.delete"]
        return ["project.create"]
