from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InteractionPromptService:
    command_message_builder: Any

    def build_command_ambiguity_response(self, candidates) -> str:
        choices = self.format_ambiguity_choices(candidates)
        return f"요청이 모호합니다. 어떤 작업을 원하시나요?\n{choices}"

    def build_query_ambiguity_question(self, candidates) -> str:
        domains = {
            candidate.entry.id.split(".")[0]
            for candidate in candidates
            if getattr(candidate, "entry", None) is not None
        }
        if domains == {"project", "application"}:
            return "프로젝트 상태인가요, 앱 상태인가요?"
        choices = self.format_ambiguity_choices(candidates)
        return f"조회 요청이 모호합니다. 어떤 대상을 조회할까요?\n{choices}"

    def build_inquiry_operation_context(self, message_text: str, *, registry_service: Any) -> list[dict[str, Any]]:
        candidates = [
            *registry_service.find_scored_candidates(message_text, usable_in="command"),
            *registry_service.find_scored_candidates(message_text, usable_in="query"),
        ]
        seen: set[str] = set()
        supported_operations: list[dict[str, Any]] = []
        for candidate in candidates:
            entry = candidate.entry
            if entry.id in seen:
                continue
            seen.add(entry.id)
            supported_operations.append(
                {
                    "id": entry.id,
                    "capability": entry.capability,
                    "requires_confirmation": entry.requires_confirmation,
                    "important_inputs": self.command_message_builder.collect_inquiry_inputs(entry),
                }
            )
        return supported_operations[:3]

    def format_ambiguity_choices(self, candidates) -> str:
        lines = []
        for index, candidate in enumerate(candidates, 1):
            lines.append(f"{index}. {self.ambiguity_label(candidate.entry.id)}")
        return "\n".join(lines)

    @staticmethod
    def ambiguity_label(operation_id: str) -> str:
        labels = {
            "project.create": "프로젝트 생성",
            "project.delete": "프로젝트 삭제",
            "project.update_name": "프로젝트 이름 변경",
            "project.update_resource": "프로젝트 리소스 변경",
            "project.add_member": "프로젝트 멤버 추가",
            "project.remove_member": "프로젝트 멤버 제거",
            "project.transfer_ownership": "프로젝트 소유권 이전",
            "application.create_apps": "애플리케이션 생성",
            "application.delete_apps": "애플리케이션 삭제",
            "application.patch_apps_resources": "애플리케이션 리소스 변경",
            "application.patch_apps_github": "애플리케이션 GitHub 연결 변경",
        }
        return labels.get(operation_id, operation_id)
