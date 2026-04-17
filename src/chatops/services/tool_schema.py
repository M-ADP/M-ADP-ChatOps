"""RegistryEntry를 Bedrock Converse API toolSpec 포맷으로 변환한다.

Agent Loop에서 LLM에게 사용 가능한 도구 목록을 제공하기 위해 사용된다.
"""
from __future__ import annotations

from typing import Any

from chatops.services.registry import RegistryEntry

# Bedrock tool name에 사용할 수 없는 문자를 대체
_NAME_SEPARATOR = "__"

# RegistryEntry의 reference 필드 정의 (플랫 스키마에 추가)
_REFERENCE_FIELDS: dict[str, dict[str, str]] = {
    "project_name": {
        "type": "string",
        "description": "대상 프로젝트 이름",
    },
    "application_name": {
        "type": "string",
        "description": "대상 애플리케이션(앱) 이름",
    },
    "target_nickname": {
        "type": "string",
        "description": "대상 사용자 닉네임",
    },
}

# operation_id별로 어떤 reference 필드가 필요한지 매핑
_OPERATION_REFERENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "project.list_projects": (),
    "project.get": ("project_name",),
    "project.get_resource_limit": ("project_name",),
    "project.check_available": ("project_name",),
    "project.check_owner": ("project_name",),
    "project.list_members": ("project_name",),
    "project.create": ("project_name",),
    "project.update_name": ("project_name",),
    "project.update_resource": ("project_name",),
    "project.delete": ("project_name",),
    "project.add_member": ("project_name", "target_nickname"),
    "project.remove_member": ("project_name", "target_nickname"),
    "project.transfer_ownership": ("project_name", "target_nickname"),
    "application.get_apps": ("project_name",),
    "application.get_apps_status": ("project_name", "application_name"),
    "application.get_apps_logs": ("project_name", "application_name"),
    "application.get_apps_details": ("project_name", "application_name"),
    "application.create_apps": ("project_name",),
    "application.delete_apps": ("project_name", "application_name"),
    "application.patch_apps_resources": ("project_name", "application_name"),
    "application.patch_apps_github": ("project_name", "application_name"),
    "monitoring.get_app_deployment_traffic": ("project_name", "application_name"),
}

# 타입 매핑
_TYPE_MAP: dict[str, str] = {
    "integer": "integer",
    "number": "number",
    "string": "string",
    "boolean": "boolean",
}


def entry_id_to_tool_name(entry_id: str) -> str:
    """RegistryEntry.id (e.g. 'project.create') → Bedrock tool name (e.g. 'project__create')."""
    return entry_id.replace(".", _NAME_SEPARATOR)


def tool_name_to_entry_id(tool_name: str) -> str:
    """Bedrock tool name (e.g. 'project__create') → RegistryEntry.id (e.g. 'project.create')."""
    return tool_name.replace(_NAME_SEPARATOR, ".")


class ToolSchemaGenerator:
    """RegistryEntry 리스트를 Bedrock Converse API toolSpec 리스트로 변환한다."""

    def generate_tool_specs(self, entries: list[RegistryEntry]) -> list[dict[str, Any]]:
        return [self._entry_to_tool_spec(entry) for entry in entries]

    def _entry_to_tool_spec(self, entry: RegistryEntry) -> dict[str, Any]:
        return {
            "toolSpec": {
                "name": entry_id_to_tool_name(entry.id),
                "description": self._build_description(entry),
                "inputSchema": {
                    "json": self._build_input_schema(entry),
                },
            }
        }

    def _build_description(self, entry: RegistryEntry) -> str:
        parts: list[str] = []
        if entry.capability:
            parts.append(entry.capability)
        if entry.summary and entry.summary != entry.capability:
            parts.append(entry.summary)
        if entry.when_to_use:
            parts.extend(entry.when_to_use)
        if entry.examples:
            parts.append(f"예시: {', '.join(entry.examples)}")
        if entry.risk_level and entry.risk_level != "low":
            parts.append(f"위험도: {entry.risk_level}")
        if entry.requires_confirmation:
            parts.append("승인 필요")
        # Bedrock은 description 최대 1024자
        description = " | ".join(parts)
        return description[:1024]

    def _build_input_schema(self, entry: RegistryEntry) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []

        # 1. Reference 필드 추가
        ref_fields = _OPERATION_REFERENCE_FIELDS.get(entry.id, ())
        for ref_name in ref_fields:
            if ref_name in _REFERENCE_FIELDS:
                properties[ref_name] = dict(_REFERENCE_FIELDS[ref_name])

        # 2. Path 파라미터
        for param in entry.required_inputs.get("path", []):
            name = str(param.get("name", ""))
            if not name or name in properties:
                continue
            properties[name] = self._param_to_property(param)
            if param.get("required", False):
                required.append(name)

        # 3. Query 파라미터
        for param in entry.required_inputs.get("query", []):
            name = str(param.get("name", ""))
            if not name or name in properties:
                continue
            properties[name] = self._param_to_property(param)
            if param.get("required", False):
                required.append(name)

        # 4. Body 필드 (required_fields + important_inputs.body)
        body_spec = entry.required_inputs.get("body")
        if isinstance(body_spec, dict):
            body_required = body_spec.get("required_fields", [])
            important_body = (
                entry.important_inputs.get("body", [])
                if isinstance(entry.important_inputs, dict)
                else []
            )
            all_body_fields = list(dict.fromkeys([*body_required, *important_body]))
            for field_name in all_body_fields:
                if field_name in properties:
                    continue
                properties[field_name] = self._body_field_to_property(field_name)
                if field_name in body_required:
                    required.append(field_name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    def _param_to_property(self, param: dict[str, Any]) -> dict[str, Any]:
        prop: dict[str, Any] = {
            "type": _TYPE_MAP.get(str(param.get("type", "string")), "string"),
        }
        description = param.get("description")
        if description:
            prop["description"] = str(description)
        return prop

    def _body_field_to_property(self, field_name: str) -> dict[str, Any]:
        # 잘 알려진 필드에 대한 타입/설명 매핑
        known_fields: dict[str, dict[str, str]] = {
            "name": {"type": "string", "description": "이름"},
            "max_cpu": {"type": "number", "description": "최대 CPU (코어)"},
            "max_memory": {"type": "number", "description": "최대 메모리 (GB)"},
            "max_disk": {"type": "number", "description": "최대 디스크 (GB)"},
            "cpu": {"type": "number", "description": "CPU (코어)"},
            "memory": {"type": "number", "description": "메모리 (GB)"},
            "disk": {"type": "number", "description": "디스크 (GB)"},
            "port": {"type": "integer", "description": "포트 번호"},
            "owner": {"type": "string", "description": "GitHub 소유자"},
            "repository": {"type": "string", "description": "GitHub 저장소 이름"},
            "branch": {"type": "string", "description": "GitHub 브랜치"},
            "project_id": {"type": "integer", "description": "프로젝트 ID"},
        }
        if field_name in known_fields:
            return dict(known_fields[field_name])
        return {"type": "string", "description": field_name}


def map_tool_inputs_to_resolved(
    operation: RegistryEntry,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """LLM이 제공한 플랫 tool_input을 DownstreamDispatcher가 기대하는 resolved_inputs로 재구성한다.

    resolved_inputs 구조:
    {
        "path": {"project_id": 1, ...},
        "query": {"start": "...", ...},
        "body": {"name": "...", "max_cpu": 4, ...},
        "references": {"project_name": "...", "application_name": "...", ...},
    }
    """
    if not tool_input:
        return {}

    resolved: dict[str, Any] = {}

    # References 추출
    references: dict[str, Any] = {}
    ref_field_names = set(_REFERENCE_FIELDS.keys())
    for key in ref_field_names:
        if key in tool_input:
            references[key] = tool_input[key]
    if references:
        resolved["references"] = references

    # Path 파라미터 추출
    path_names = {str(p.get("name", "")) for p in operation.required_inputs.get("path", [])}
    path_values = {k: tool_input[k] for k in path_names if k in tool_input}
    if path_values:
        resolved["path"] = path_values

    # Query 파라미터 추출
    query_names = {str(p.get("name", "")) for p in operation.required_inputs.get("query", [])}
    query_values = {k: tool_input[k] for k in query_names if k in tool_input}
    if query_values:
        resolved["query"] = query_values

    # Body 파라미터 추출 (path/query/reference가 아닌 나머지)
    non_body_keys = path_names | query_names | ref_field_names
    body_values = {k: v for k, v in tool_input.items() if k not in non_body_keys}
    if body_values:
        resolved["body"] = body_values

    return resolved
