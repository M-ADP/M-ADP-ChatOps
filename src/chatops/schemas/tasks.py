from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskInputField(BaseModel):
    key: str
    label: str
    value: Any | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "key": "cpu",
                "label": "CPU",
                "value": 1,
            }
        }
    )


class TaskSnapshot(BaseModel):
    kind: str = "operation"
    title: str
    status: str
    request_type: str | None = None
    approval_state: str
    operation_id: str | None = None
    risk_level: str | None = None
    target: dict[str, Any] | None = None
    filled_inputs: dict[str, Any] | None = None
    missing_inputs: list[TaskInputField] | None = None
    next_actions: list[str] = []
    summary: str | None = None
    clarification_type: str | None = None
    is_ambiguous: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "kind": "operation",
                "title": "애플리케이션 생성",
                "status": "pending_approval",
                "request_type": "command",
                "approval_state": "awaiting_approval",
                "operation_id": "application.create_apps",
                "risk_level": "medium",
                "target": {
                    "project_name": "demo",
                    "application_name": "api",
                },
                "filled_inputs": {
                    "name": "api",
                    "cpu": 1,
                    "memory": 512,
                    "disk": 10,
                },
                "missing_inputs": [],
                "next_actions": ["approve", "edit", "cancel"],
                "summary": "demo 프로젝트에 api 앱을 생성하는 승인 대기 작업입니다.",
                "clarification_type": None,
                "is_ambiguous": False,
            }
        }
    )
