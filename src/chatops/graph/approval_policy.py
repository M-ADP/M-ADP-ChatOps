from __future__ import annotations

import json
from typing import Any


class ApprovalPolicyService:
    def build_confirmation_payload(
        self,
        *,
        operation_id: str,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, str]:
        references = resolved_inputs.get("references", {})
        payload: dict[str, str] = {"operation": operation_id}
        if references.get("project_name"):
            payload["project_name"] = str(references["project_name"])
        if references.get("application_name"):
            payload["application_name"] = str(references["application_name"])
        if references.get("target_nickname"):
            payload["target_user"] = str(references["target_nickname"])
        return payload if len(payload) > 1 else {}

    def format_confirmation_payload(self, payload: dict[str, str]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def matches_confirmation(self, approved: str, expected_payload: dict[str, str]) -> bool:
        raw = approved.strip()
        if not raw:
            return False
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            normalized = {str(key): str(value) for key, value in parsed.items()}
            return normalized == expected_payload
        target_name = self.extract_target_name(
            operation_id=str(expected_payload.get("operation", "")),
            resolved_inputs={
                "references": {
                    "project_name": expected_payload.get("project_name"),
                    "application_name": expected_payload.get("application_name"),
                    "target_nickname": expected_payload.get("target_user"),
                }
            },
        )
        return target_name is not None and raw == target_name

    def extract_target_name(
        self,
        *,
        operation_id: str,
        resolved_inputs: dict[str, Any],
    ) -> str | None:
        confirmation_payload = self.build_confirmation_payload(
            operation_id=operation_id,
            resolved_inputs=resolved_inputs,
        )
        relevant_values = [
            value
            for key, value in confirmation_payload.items()
            if key in {"project_name", "application_name", "target_user"}
        ]
        if len(relevant_values) == 1:
            return str(relevant_values[0])
        return None

    def build_high_risk_plan(
        self,
        *,
        operation_id: str,
        plan_detail: str,
        resolved_inputs: dict[str, Any],
    ) -> str:
        confirmation_payload = self.build_confirmation_payload(
            operation_id=operation_id,
            resolved_inputs=resolved_inputs,
        )
        warning = (
            "⚠️ 이 작업은 되돌릴 수 없습니다.\n"
            f"{plan_detail}\n"
        )
        if confirmation_payload:
            warning += (
                "계속하려면 아래 확인값을 정확히 입력해주세요.\n"
                f"{self.format_confirmation_payload(confirmation_payload)}"
            )
        else:
            warning += "계속하려면 '실행' 또는 '확인'을 입력해주세요."
        return warning
