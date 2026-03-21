from __future__ import annotations

import json
import re
from typing import Any

from chatops.services.registry import RegistryEntry


KEY_VALUE_PATTERN = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?P<value>[^\s,}]+)")
JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


class ParameterResolverService:
    def resolve(self, operation: RegistryEntry, message_text: str) -> dict[str, Any]:
        parsed_pairs = self._extract_pairs(message_text)
        resolved: dict[str, Any] = {}

        path_values = self._resolve_named_fields(operation.required_inputs.get("path", []), parsed_pairs)
        if path_values:
            resolved["path"] = path_values

        query_values = self._resolve_named_fields(operation.required_inputs.get("query", []), parsed_pairs)
        if query_values:
            resolved["query"] = query_values

        body_spec = operation.required_inputs.get("body")
        if isinstance(body_spec, dict):
            body_values = self._resolve_body(body_spec, parsed_pairs)
            if body_values:
                resolved["body"] = body_values

        return resolved

    def _extract_pairs(self, message_text: str) -> dict[str, Any]:
        pairs: dict[str, Any] = {}
        for match in KEY_VALUE_PATTERN.finditer(message_text):
            pairs[match.group("key")] = self._coerce(match.group("value"))

        json_match = JSON_BLOCK_PATTERN.search(message_text)
        if json_match:
            try:
                loaded = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    pairs[str(key)] = value
        return pairs

    def _resolve_named_fields(self, fields: list[dict[str, Any]], parsed_pairs: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for field in fields:
            field_name = str(field["name"])
            if field_name in parsed_pairs:
                resolved[field_name] = parsed_pairs[field_name]
        return resolved

    def _resolve_body(self, body_spec: dict[str, Any], parsed_pairs: dict[str, Any]) -> dict[str, Any]:
        required_fields = body_spec.get("required_fields", [])
        resolved: dict[str, Any] = {}
        for field_name in required_fields:
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
