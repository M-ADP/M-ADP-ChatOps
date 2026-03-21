from __future__ import annotations

from pathlib import Path

from ai_registry.openapi_loader import load_operations


def test_load_operations_extracts_project_create() -> None:
    operations = load_operations(Path("apis/project.yaml"))

    project_create = next(op for op in operations if op.id == "project.create")

    assert project_create.method == "POST"
    assert project_create.path == "/projects"
    assert "X-User-Id" in project_create.required_headers
    assert "body" in project_create.required_inputs


def test_load_operations_keeps_semantic_suffixes_for_project_checks() -> None:
    operations = load_operations(Path("apis/project.yaml"))
    operation_ids = {op.id for op in operations}

    assert "project.check_available" in operation_ids
    assert "project.check_owner" in operation_ids


def test_load_operations_extracts_required_body_fields_from_schema_ref() -> None:
    operations = load_operations(Path("apis/application.yaml"))

    create_app = next(op for op in operations if op.id == "application.create_apps")
    body = create_app.required_inputs["body"]

    assert body["required"] is True
    assert body["required_fields"] == [
        "name",
        "cpu",
        "memory",
        "disk",
        "project_id",
        "port",
    ]
