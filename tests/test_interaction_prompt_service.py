from __future__ import annotations

from dataclasses import dataclass

from chatops.graph.command_message_builder import CommandMessageBuilder
from chatops.graph.interaction_prompt_service import InteractionPromptService
from chatops.services.registry import RegistryEntry, ScoredCandidate


def _entry(entry_id: str, *, usable_in: tuple[str, ...] = ("query",)) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path="/test",
        method="GET",
        summary=entry_id,
        capability=entry_id,
        usable_in=usable_in,
        operation_kind="read" if usable_in == ("query",) else "write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=usable_in != ("query",),
        risk_level="low",
        side_effects=(),
        required_headers=(),
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={"body": ["name"]} if usable_in != ("query",) else {},
    )


@dataclass
class _Registry:
    candidates: list[ScoredCandidate]

    def find_scored_candidates(self, message_text: str, usable_in: str):
        del message_text, usable_in
        return list(self.candidates)


def test_interaction_prompt_service_formats_query_ambiguity_for_project_and_app() -> None:
    service = InteractionPromptService(command_message_builder=CommandMessageBuilder())
    candidates = [
        ScoredCandidate(entry=_entry("project.get"), score=10),
        ScoredCandidate(entry=_entry("application.get_apps_status"), score=9),
    ]

    question = service.build_query_ambiguity_question(candidates)

    assert question == "프로젝트 상태인가요, 앱 상태인가요?"


def test_interaction_prompt_service_builds_inquiry_operation_context_without_duplicates() -> None:
    entry = _entry("project.create", usable_in=("command",))
    registry = _Registry(
        candidates=[
            ScoredCandidate(entry=entry, score=10),
            ScoredCandidate(entry=entry, score=9),
        ]
    )
    service = InteractionPromptService(command_message_builder=CommandMessageBuilder())

    supported = service.build_inquiry_operation_context(
        "프로젝트 생성 방법 알려줘",
        registry_service=registry,
    )

    assert supported == [
        {
            "id": "project.create",
            "capability": "project.create",
            "requires_confirmation": True,
            "important_inputs": ["프로젝트 이름"],
        }
    ]
