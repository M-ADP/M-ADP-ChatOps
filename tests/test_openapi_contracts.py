from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUCCESS_SCHEMA_PREFIXES = (
    "SuccessResponse_",
    "MadpResponse_",
    "ResponseEntityApiResponseDto",
)


def _load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def _iter_operations(spec: dict) -> list[dict]:
    operations: list[dict] = []
    for methods in spec["paths"].values():
        for method_name, operation in methods.items():
            if method_name in {"get", "post", "patch", "delete"}:
                operations.append(operation)
    return operations


def _header_names(operation: dict) -> set[str]:
    return {
        parameter["name"]
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "header"
    }


def _header_types(operation: dict) -> dict[str, str | None]:
    header_types: dict[str, str | None] = {}
    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "header":
            continue
        schema = parameter.get("schema", {})
        header_types[str(parameter["name"])] = schema.get("type")
    return header_types


def _success_schema_ref(operation: dict) -> str | None:
    for status_code, response in operation.get("responses", {}).items():
        if not str(status_code).startswith("2"):
            continue
        schema = response.get("content", {}).get("application/json", {}).get("schema", {})
        return schema.get("$ref")
    return None


def test_project_application_and_monitoring_specs_expose_required_user_headers_as_strings() -> None:
    application_spec = _load_yaml("apis/application.yaml")
    project_spec = _load_yaml("apis/project.yaml")
    monitoring_spec = _load_yaml("apis/monitoring.yaml")

    all_operations = [
        *_iter_operations(project_spec),
        *_iter_operations(application_spec),
        *_iter_operations(monitoring_spec),
    ]

    assert all_operations
    for operation in all_operations:
        assert _header_names(operation) >= {"X-User-Id", "X-User-Role"}
        assert _header_types(operation)["X-User-Id"] == "string"
        assert _header_types(operation)["X-User-Role"] == "string"


def test_project_application_and_monitoring_specs_use_envelope_schemas_for_success_responses() -> None:
    project_spec = _load_yaml("apis/project.yaml")
    application_spec = _load_yaml("apis/application.yaml")
    monitoring_spec = _load_yaml("apis/monitoring.yaml")

    all_operations = [
        *_iter_operations(project_spec),
        *_iter_operations(application_spec),
        *_iter_operations(monitoring_spec),
    ]

    for operation in all_operations:
        schema_ref = _success_schema_ref(operation)
        assert schema_ref is not None
        schema_name = schema_ref.rsplit("/", 1)[-1]
        assert schema_name.startswith(ALLOWED_SUCCESS_SCHEMA_PREFIXES)


def test_monitoring_registry_matches_openapi_contract() -> None:
    monitoring_spec = _load_yaml("apis/monitoring.yaml")
    registry_entry = _load_yaml("ai_registry/monitoring.get_app_deployment_traffic.ai.yaml")

    operation = _iter_operations(monitoring_spec)[0]
    assert registry_entry["source_file"] == "apis/monitoring.yaml"
    assert registry_entry["operation_id"] == operation["operationId"]
    assert registry_entry["required_headers"] == ["X-User-Id", "X-User-Role"]

    header_inputs = {item["name"]: item["type"] for item in registry_entry["required_inputs"]["headers"]}
    assert header_inputs == {"X-User-Id": "string", "X-User-Role": "string"}

    query_inputs = {item["name"]: item["type"] for item in registry_entry["required_inputs"]["query"]}
    assert query_inputs == {"start": "string", "end": "string"}
