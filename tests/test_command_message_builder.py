from __future__ import annotations

from chatops.graph.command_message_builder import CommandMessageBuilder
from chatops.services.registry import RegistryEntry


def _entry(entry_id: str) -> RegistryEntry:
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
        risk_level="medium",
        side_effects=(),
        required_headers=(),
        required_inputs={"headers": [], "path": [], "query": [], "body": {"required": True, "required_fields": []}},
        important_inputs={},
    )


def test_command_message_builder_formats_project_create_plan() -> None:
    builder = CommandMessageBuilder()
    operation = _entry("project.create")
    resolved_inputs = {
        "body": {
            "name": "demo",
            "max_cpu": 1,
            "max_memory": 0.5,
            "max_disk": 10,
        }
    }

    message = builder.build_command_plan(operation, resolved_inputs)

    assert "프로젝트 이름 demo" in message
    assert "최대 CPU 1" in message
    assert "최대 메모리 0.5GB" in message
    assert "최대 디스크 10GB" in message


def test_command_message_builder_formats_failure_message() -> None:
    builder = CommandMessageBuilder()

    message = builder.build_command_failure_message(
        "project.remove_member",
        "대상 사용자를 찾지 못했습니다.",
    )

    assert message == "프로젝트 멤버 제거에 실패했습니다. 대상 사용자를 찾지 못했습니다. 입력값을 확인하고 다시 시도해주세요."
