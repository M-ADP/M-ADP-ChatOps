from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chatops.graph.command_message_builder import CommandMessageBuilder
from chatops.services.registry import RegistryEntry


@dataclass(frozen=True)
class TaskSnapshotBuilder:
    command_message_builder: CommandMessageBuilder

    def build(
        self,
        *,
        operation: RegistryEntry | None,
        request_status: str,
        request_type: str | None,
        resolved_inputs: dict[str, Any] | None = None,
        missing_inputs: list[str] | None = None,
        risk_level: str | None = None,
        clarification_type: str | None = None,
        is_ambiguous: bool = False,
        summary: str | None = None,
    ) -> dict[str, Any] | None:
        if operation is None:
            return None

        return {
            "kind": "operation",
            "title": operation.summary or operation.capability or operation.id,
            "operation_id": operation.id,
            "status": request_status,
            "request_type": request_type,
            "approval_state": self._approval_state(request_status),
            "risk_level": risk_level or operation.risk_level,
            "target": self._target(operation, resolved_inputs),
            "filled_inputs": self._filled_inputs(resolved_inputs),
            "missing_inputs": self._missing_input_fields(operation, missing_inputs),
            "next_actions": self._next_actions(request_status, request_type),
            "summary": summary,
            "clarification_type": clarification_type,
            "is_ambiguous": is_ambiguous,
        }

    def _filled_inputs(self, resolved_inputs: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(resolved_inputs, dict):
            return None
        values: dict[str, Any] = {}
        for section_name in ("query", "body"):
            section = resolved_inputs.get(section_name)
            if isinstance(section, dict):
                values.update(section)
        return values or None

    def _target(self, operation: RegistryEntry, resolved_inputs: dict[str, Any] | None) -> dict[str, Any] | None:
        refs = {}
        body = {}
        if isinstance(resolved_inputs, dict):
            raw_refs = resolved_inputs.get("references")
            raw_body = resolved_inputs.get("body")
            if isinstance(raw_refs, dict):
                refs = raw_refs
            if isinstance(raw_body, dict):
                body = raw_body

        target: dict[str, Any] = {}
        if refs.get("project_name") is not None:
            target["project_name"] = refs["project_name"]
        elif operation.id == "project.create" and body.get("name") is not None:
            target["project_name"] = body["name"]

        if refs.get("application_name") is not None:
            target["application_name"] = refs["application_name"]
        elif operation.id == "application.create_apps" and body.get("name") is not None:
            target["application_name"] = body["name"]

        if refs.get("target_nickname") is not None:
            target["target_nickname"] = refs["target_nickname"]

        return target or None

    def _missing_input_fields(
        self,
        operation: RegistryEntry,
        missing_inputs: list[str] | None,
    ) -> list[dict[str, Any]] | None:
        if not missing_inputs:
            return None
        return [
            {
                "key": field_name,
                "label": self.command_message_builder.format_missing_input_prompt_label(operation.id, field_name),
            }
            for field_name in missing_inputs
        ]

    @staticmethod
    def _approval_state(request_status: str) -> str:
        mapping = {
            "input_required": "not_ready",
            "ambiguous": "needs_clarification",
            "pending_approval": "awaiting_approval",
            "executing": "approved",
            "completed": "completed",
            "failed": "failed",
            "escalated": "failed",
            "rejected": "cancelled",
            "approval_expired": "expired",
        }
        return mapping.get(request_status, "not_ready")

    @staticmethod
    def _next_actions(request_status: str, request_type: str | None) -> list[str]:
        if request_status == "pending_approval":
            return ["approve", "edit", "cancel"]
        if request_status == "input_required":
            return ["fill_inputs", "cancel"]
        if request_status == "ambiguous":
            return ["choose_option", "cancel"]
        if request_status == "executing":
            return ["view_progress"]
        if request_status == "completed":
            return ["view_result"] if request_type == "command" else ["refine", "compare", "export"]
        if request_status == "failed":
            return ["retry"]
        if request_status == "escalated":
            return ["retry"]
        if request_status == "rejected":
            return ["retry"]
        return []
