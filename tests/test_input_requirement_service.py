from __future__ import annotations

from chatops.graph.input_requirement_service import InputRequirementService
from chatops.services.registry import RegistryEntry


def _entry() -> RegistryEntry:
    return RegistryEntry(
        id="project.create",
        source_file="test",
        operation_id="project.create",
        path="/projects",
        method="POST",
        summary="프로젝트 생성",
        capability="프로젝트 생성",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=(),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["name"]},
        },
        important_inputs={"path": [], "query": [], "body": ["name", "max_cpu", "max_memory", "max_disk"]},
    )


def test_input_requirement_service_reports_missing_business_fields() -> None:
    service = InputRequirementService()

    missing = service.missing_required_inputs(_entry(), {"body": {"name": "demo"}})

    assert missing == ["max_cpu", "max_memory", "max_disk"]


def test_input_requirement_service_treats_references_as_satisfying_ids() -> None:
    entry = RegistryEntry(
        id="application.get_apps_status",
        source_file="test",
        operation_id="application.get_apps_status",
        path="/apps/status",
        method="GET",
        summary="앱 상태 조회",
        capability="앱 상태 조회",
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=(),
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={"path": [{"name": "project_id"}, {"name": "application_id"}], "query": [], "body": []},
    )
    service = InputRequirementService()

    missing = service.missing_required_inputs(
        entry,
        {"references": {"project_name": "demo", "application_name": "api-server"}},
    )

    assert missing == []
