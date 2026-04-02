from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InputRequirementService:
    def missing_required_inputs(self, operation, resolved_inputs: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        required_inputs = operation.required_inputs
        important_inputs = operation.important_inputs or {}
        path_values = resolved_inputs.get("path", {})
        query_values = resolved_inputs.get("query", {})
        body_values = resolved_inputs.get("body", {})
        references = resolved_inputs.get("references", {})

        for field in required_inputs.get("path", []):
            field_name = str(field.get("name", ""))
            if not field.get("required", True) or not field_name:
                continue
            if field_name in path_values or self.is_reference_satisfied(field_name, references):
                continue
            missing.append(self.to_user_input_field(field_name))

        for field in required_inputs.get("query", []):
            field_name = str(field.get("name", ""))
            if not field.get("required", False) or not field_name:
                continue
            if field_name in query_values or self.is_reference_satisfied(field_name, references):
                continue
            missing.append(self.to_user_input_field(field_name))

        body_spec = required_inputs.get("body")
        if isinstance(body_spec, dict):
            for field_name in body_spec.get("required_fields", []):
                normalized = str(field_name)
                if normalized in body_values or self.is_reference_satisfied(normalized, references):
                    continue
                missing.append(self.to_user_input_field(normalized))

        for field_name in important_inputs.get("path", []):
            normalized = self.normalize_input_name(field_name)
            if not normalized:
                continue
            if normalized in path_values or self.is_reference_satisfied(normalized, references):
                continue
            missing.append(self.to_user_input_field(normalized))

        for field_name in important_inputs.get("query", []):
            normalized = self.normalize_input_name(field_name)
            if not normalized:
                continue
            if normalized in query_values or self.is_reference_satisfied(normalized, references):
                continue
            missing.append(self.to_user_input_field(normalized))

        for field_name in important_inputs.get("body", []):
            normalized = self.normalize_input_name(field_name)
            if not normalized:
                continue
            if normalized in body_values or self.is_reference_satisfied(normalized, references):
                continue
            missing.append(self.to_user_input_field(normalized))

        return list(dict.fromkeys(missing))

    @staticmethod
    def is_reference_satisfied(field_name: str, references: dict[str, Any]) -> bool:
        reference_aliases = {
            "project_id": "project_name",
            "application_id": "application_name",
            "appDeploymentId": "application_name",
            "app_deployment_name": "application_name",
            "user_id": "target_nickname",
            "target_user_id": "target_nickname",
        }
        alias = reference_aliases.get(field_name)
        return bool(alias and references.get(alias))

    @staticmethod
    def to_user_input_field(field_name: str) -> str:
        aliases = {
            "project_id": "project_name",
            "application_id": "application_name",
            "appDeploymentId": "application_name",
            "app_deployment_name": "application_name",
            "user_id": "target_nickname",
            "target_user_id": "target_nickname",
        }
        return aliases.get(field_name, field_name)

    @staticmethod
    def normalize_input_name(field_name: Any) -> str:
        if isinstance(field_name, dict):
            return str(field_name.get("name", ""))
        return str(field_name)
