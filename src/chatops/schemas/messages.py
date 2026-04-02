from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from chatops.schemas.runtime import PlanObject, SpecialistResult, VerifierDecision
from chatops.schemas.tasks import TaskSnapshot


class ConversationMessage(BaseModel):
    message_id: str
    request_id: int | None = None
    role: str
    type: str
    text: str | None = None
    task: TaskSnapshot | None = None
    plan: PlanObject | None = None
    verifier: VerifierDecision | None = None
    specialist: SpecialistResult | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message_id": "msg_1001",
                "request_id": 2001,
                "role": "assistant",
                "type": "task",
                "text": "계획을 검토하고 승인하면 바로 실행합니다.",
                "task": {
                    "title": "애플리케이션 생성",
                    "status": "pending_approval",
                    "approval_state": "awaiting_approval",
                    "next_actions": ["approve", "edit", "cancel"],
                },
                "created_at": "2026-04-02T10:01:02Z",
                "updated_at": "2026-04-02T10:01:02Z",
            }
        }
    )


class CreateSessionMessageRequest(BaseModel):
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "demo 프로젝트에 api 앱 만들어줘",
            }
        }
    )


class CreateSessionMessageResponse(BaseModel):
    messages: list[ConversationMessage]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "messages": [
                    {
                        "message_id": "msg_user_01",
                        "role": "user",
                        "type": "text",
                        "text": "demo 프로젝트에 api 앱 만들어줘",
                        "created_at": "2026-04-02T10:01:00Z",
                        "updated_at": "2026-04-02T10:01:00Z",
                    },
                    {
                        "message_id": "msg_agent_01",
                        "request_id": 2001,
                        "role": "assistant",
                        "type": "task",
                        "text": "계획을 검토하고 승인하면 바로 실행합니다.",
                        "task": {
                            "title": "애플리케이션 생성",
                            "status": "pending_approval",
                            "approval_state": "awaiting_approval",
                            "next_actions": ["approve", "edit", "cancel"],
                        },
                        "created_at": "2026-04-02T10:01:02Z",
                        "updated_at": "2026-04-02T10:01:02Z",
                    },
                ]
            }
        }
    )


class SessionMessagesPageResponse(BaseModel):
    messages: list[ConversationMessage]
    next_cursor: str | None = None
    has_more: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "messages": [
                    {
                        "message_id": "msg_user_00",
                        "role": "user",
                        "type": "text",
                        "text": "이전 메시지",
                        "created_at": "2026-04-02T09:58:00Z",
                        "updated_at": "2026-04-02T09:58:00Z",
                    }
                ],
                "next_cursor": None,
                "has_more": False,
            }
        }
    )
