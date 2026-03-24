from __future__ import annotations

import json
import re
from typing import Any

from chatops.services.registry import RegistryEntry


KEY_VALUE_PATTERN = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?P<value>[^\s,}]+)")
JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
NAME_PATTERNS = (
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)"),
    re.compile(r"(?<![A-Za-z0-9._-])name\s*(?:은|는)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)", re.IGNORECASE),
)
NUMERIC_FIELD_PATTERNS = {
    "max_cpu": (
        re.compile(r"(?:max_cpu|cpu)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE),
    ),
    "max_memory": (
        re.compile(r"(?:max_memory|memory|메모리)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE),
    ),
    "max_disk": (
        re.compile(r"(?:max_disk|disk|디스크)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE),
    ),
    "cpu": (
        re.compile(r"(?:cpu)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE),
    ),
    "memory": (
        re.compile(r"(?:memory|메모리)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE),
    ),
    "disk": (
        re.compile(r"(?:disk|디스크)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE),
    ),
    "port": (
        re.compile(r"(?:port|포트)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+)", re.IGNORECASE),
    ),
}
RENAMED_NAME_PATTERNS = (
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)\s*로\s*(?:바꿔줘|바꿔|변경해줘|변경해|수정해줘|수정해|고쳐줘|고쳐)"),
)
PROJECT_NAME_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*프로젝트(?:에|를|을|은|는|이|가|\s|$)"),
)
APPLICATION_NAME_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*(?:앱|애플리케이션)(?:에|를|을|은|는|이|가|\s|$)"),
)
TARGET_NICKNAME_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*멤버\s*추가"),
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*멤버\s*(?:제거|삭제|지워)"),
    re.compile(r"소유권(?:을|은|는)?\s*(?P<value>[A-Za-z0-9._-]+)에게\s*(?:넘겨줘|넘겨|이전해줘|이전해)"),
    re.compile(r"(?:대상 사용자|닉네임)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)"),
)
TEXT_FIELD_PATTERNS = {
    "owner": (
        re.compile(r"(?:owner|깃허브 소유자|GitHub 소유자)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+)", re.IGNORECASE),
    ),
    "repository": (
        re.compile(r"(?:repository|repo|저장소 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+)", re.IGNORECASE),
    ),
    "branch": (
        re.compile(r"(?:branch|브랜치)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._/-]+)", re.IGNORECASE),
    ),
}


class ParameterResolverService:
    def resolve(
        self,
        operation: RegistryEntry,
        message_text: str,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed_pairs = self._extract_pairs(message_text)
        references = self._extract_references(message_text)
        self._apply_session_context(message_text, parsed_pairs, references, session_context)
        self._apply_reference_aliases(operation, parsed_pairs, references)
        resolved: dict[str, Any] = {}

        path_values = self._resolve_named_fields(operation.required_inputs.get("path", []), parsed_pairs)
        if path_values:
            resolved["path"] = path_values

        query_values = self._resolve_named_fields(operation.required_inputs.get("query", []), parsed_pairs)
        if query_values:
            resolved["query"] = query_values

        body_spec = operation.required_inputs.get("body")
        if isinstance(body_spec, dict):
            body_values = self._resolve_body(body_spec, operation.important_inputs, parsed_pairs)
            if body_values:
                resolved["body"] = body_values

        if references:
            resolved["references"] = references

        return resolved

    def _extract_pairs(self, message_text: str) -> dict[str, Any]:
        pairs: dict[str, Any] = {}
        for match in KEY_VALUE_PATTERN.finditer(message_text):
            pairs[match.group("key")] = self._coerce(match.group("value"))

        loaded = None
        json_match = JSON_BLOCK_PATTERN.search(message_text)
        if json_match:
            try:
                loaded = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                loaded = None
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                pairs[str(key)] = value

        self._infer_natural_language_fields(message_text, pairs)
        return pairs

    def _apply_session_context(
        self,
        message_text: str,
        pairs: dict[str, Any],
        references: dict[str, Any],
        session_context: dict[str, Any] | None,
    ) -> None:
        if not session_context or not self._should_use_session_context(message_text):
            return
        last_message_text = session_context.get("last_message_text")
        if not isinstance(last_message_text, str) or not last_message_text.strip():
            return
        fallback_pairs = self._extract_pairs(last_message_text)
        fallback_references = self._extract_references(last_message_text)
        if "name" not in pairs and "name" in fallback_pairs:
            pairs["name"] = fallback_pairs["name"]
        if "project_name" not in references and "project_name" in fallback_references:
            references["project_name"] = fallback_references["project_name"]
        if "application_name" not in references and "application_name" in fallback_references:
            references["application_name"] = fallback_references["application_name"]
        if "target_nickname" not in references and "target_nickname" in fallback_references:
            references["target_nickname"] = fallback_references["target_nickname"]

    def _should_use_session_context(self, message_text: str) -> bool:
        return any(marker in message_text for marker in ("그거", "그걸", "그거를", "아까", "방금", "이거"))

    def _infer_natural_language_fields(self, message_text: str, pairs: dict[str, Any]) -> None:
        if "name" not in pairs:
            for pattern in (*RENAMED_NAME_PATTERNS, *NAME_PATTERNS):
                match = pattern.search(message_text)
                if match:
                    pairs["name"] = self._coerce(match.group("value"))
                    break
        for field_name, patterns in NUMERIC_FIELD_PATTERNS.items():
            if field_name in pairs:
                continue
            for pattern in patterns:
                match = pattern.search(message_text)
                if match:
                    pairs[field_name] = self._coerce(match.group("value"))
                    break
        for field_name, patterns in TEXT_FIELD_PATTERNS.items():
            if field_name in pairs:
                continue
            for pattern in patterns:
                match = pattern.search(message_text)
                if match:
                    pairs[field_name] = self._coerce(match.group("value"))
                    break

    def _extract_references(self, message_text: str) -> dict[str, Any]:
        references: dict[str, Any] = {}
        for pattern in PROJECT_NAME_PATTERNS:
            match = pattern.search(message_text)
            if match:
                references["project_name"] = self._coerce(match.group("value"))
                break
        for pattern in APPLICATION_NAME_PATTERNS:
            match = pattern.search(message_text)
            if match:
                references["application_name"] = self._coerce(match.group("value"))
                break
        for pattern in TARGET_NICKNAME_PATTERNS:
            match = pattern.search(message_text)
            if match:
                references["target_nickname"] = self._coerce(match.group("value"))
                break
        return references

    def _apply_reference_aliases(
        self,
        operation: RegistryEntry,
        pairs: dict[str, Any],
        references: dict[str, Any],
    ) -> None:
        operation_id = operation.id
        if operation_id == "project.create" and "name" not in pairs and "project_name" in references:
            pairs["name"] = references["project_name"]
        if operation_id == "project.create":
            if "cpu" in pairs and "max_cpu" not in pairs:
                pairs["max_cpu"] = pairs["cpu"]
            if "memory" in pairs and "max_memory" not in pairs:
                pairs["max_memory"] = pairs["memory"]
            if "disk" in pairs and "max_disk" not in pairs:
                pairs["max_disk"] = pairs["disk"]
        if operation_id.startswith("application.") and "name" not in pairs and "application_name" in references:
            pairs["name"] = references["application_name"]
        if operation_id == "monitoring.get_app_deployment_traffic" and "app_deployment_name" not in pairs:
            application_name = references.get("application_name")
            if application_name is not None:
                pairs["app_deployment_name"] = application_name

    def _resolve_named_fields(self, fields: list[dict[str, Any]], parsed_pairs: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for field in fields:
            field_name = str(field["name"])
            if field_name in parsed_pairs:
                resolved[field_name] = parsed_pairs[field_name]
        return resolved

    def _resolve_body(
        self,
        body_spec: dict[str, Any],
        important_inputs: dict[str, Any],
        parsed_pairs: dict[str, Any],
    ) -> dict[str, Any]:
        required_fields = body_spec.get("required_fields", [])
        important_body_fields = important_inputs.get("body", []) if isinstance(important_inputs, dict) else []
        candidate_fields = list(dict.fromkeys([*required_fields, *important_body_fields]))
        resolved: dict[str, Any] = {}
        for field_name in candidate_fields:
            if field_name in parsed_pairs:
                resolved[field_name] = parsed_pairs[field_name]
        return resolved

    def _coerce(self, value: str) -> Any:
        stripped = value.strip().strip("\"'")
        if re.fullmatch(r"-?\d+", stripped):
            return int(stripped)
        if re.fullmatch(r"-?\d+\.\d+", stripped):
            return float(stripped)
        return stripped
