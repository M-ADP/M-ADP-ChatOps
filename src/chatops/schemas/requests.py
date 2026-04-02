from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from chatops.schemas.runtime import PlanObject, SpecialistResult, VerifierDecision
from chatops.schemas.tasks import TaskSnapshot


class CreateRequestRequest(BaseModel):
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "demo 프로젝트에 api 앱 만들어줘",
            }
        }
    )


class ApproveRequestRequest(BaseModel):
    confirmation_text: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "confirmation_text": "승인",
            }
        }
    )


class RequestResponse(BaseModel):
    request_id: int
    session_id: int
    status: str
    message: str
    assistant_message: str | None = None
    request_type: str | None = None
    requires_approval: bool = False
    missing_inputs: list[str] | None = None
    final_response: str | None = None
    task: TaskSnapshot | None = None
    plan: PlanObject | None = None
    verifier: VerifierDecision | None = None
    specialist: SpecialistResult | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": 2001,
                "session_id": 1001,
                "status": "pending_approval",
                "message": "demo 프로젝트에 api 앱 만들어줘",
                "assistant_message": "계획을 검토하고 승인하면 바로 실행합니다.",
                "request_type": "command",
                "requires_approval": True,
                "missing_inputs": None,
                "final_response": "demo 프로젝트에 api 앱을 생성할게요. 실행할까요?",
                "task": {
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
                },
                "created_at": "2026-04-02T10:01:00Z",
                "updated_at": "2026-04-02T10:01:05Z",
            }
        }
    )


class ApproveRequestResponse(BaseModel):
    request_id: int
    status: str
    assistant_message: str | None = None
    task: TaskSnapshot | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": 2001,
                "status": "completed",
                "assistant_message": "api 앱 생성을 완료했습니다.",
                "task": {
                    "kind": "operation",
                    "title": "애플리케이션 생성",
                    "status": "completed",
                    "request_type": "command",
                    "approval_state": "completed",
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
                    "next_actions": ["view_result"],
                    "summary": "api 앱 생성 완료",
                    "clarification_type": None,
                    "is_ambiguous": False,
                },
            }
        }
    )


class RejectRequestResponse(BaseModel):
    request_id: int
    status: str
    assistant_message: str | None = None
    task: TaskSnapshot | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": 2001,
                "status": "rejected",
                "assistant_message": "알겠습니다. 요청을 취소했습니다.",
                "task": {
                    "kind": "operation",
                    "title": "애플리케이션 생성",
                    "status": "rejected",
                    "request_type": "command",
                    "approval_state": "cancelled",
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
                    "next_actions": ["retry"],
                    "summary": "애플리케이션 생성 요청이 취소되었습니다.",
                    "clarification_type": None,
                    "is_ambiguous": False,
                },
            }
        }
    )
