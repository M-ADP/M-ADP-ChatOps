from __future__ import annotations

from pathlib import Path

from ai_registry.openapi_loader import load_operations
from ai_registry.scaffold import build_metadata


def test_build_metadata_marks_get_as_read_query() -> None:
    operations = load_operations(Path("apis/project.yaml"))

    list_projects = next(
        op for op in operations if op.method == "GET" and op.path == "/projects"
    )
    metadata = build_metadata(list_projects)

    assert metadata["operation_kind"] == "read"
    assert metadata["usable_in"] == ["query"]
    assert metadata["requires_confirmation"] is False


def test_build_metadata_marks_delete_as_high_risk_command() -> None:
    operations = load_operations(Path("apis/project.yaml"))

    delete_project = next(
        op for op in operations if op.method == "DELETE" and op.path == "/projects/{project_id}"
    )
    metadata = build_metadata(delete_project)

    assert metadata["operation_kind"] == "delete"
    assert metadata["usable_in"] == ["command"]
    assert metadata["requires_confirmation"] is True
    assert metadata["risk_level"] == "high"


def test_build_metadata_provides_ai_usable_defaults_for_commands() -> None:
    operations = load_operations(Path("apis/project.yaml"))

    create_project = next(
        op for op in operations if op.method == "POST" and op.path == "/projects"
    )
    metadata = build_metadata(create_project)

    assert metadata["when_to_use"]
    assert metadata["missing_info_questions"]
    assert metadata["plan_template"]


def test_build_metadata_provides_response_hint_for_reads() -> None:
    operations = load_operations(Path("apis/monitoring.yaml"))

    traffic = next(op for op in operations if op.id == "monitoring.get_app_deployment_traffic")
    metadata = build_metadata(traffic)

    assert metadata["response_interpretation"]
