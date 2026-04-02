from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from chatops.schemas.messages import ConversationMessage


class CreateSessionRequest(BaseModel):
    title: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "프로젝트 생성 상담",
            }
        }
    )


class SessionResponse(BaseModel):
    session_id: int
    user_id: str
    title: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": 1001,
                "user_id": "user-1",
                "title": "프로젝트 생성 상담",
                "status": "active",
                "created_at": "2026-04-02T10:00:00Z",
                "updated_at": "2026-04-02T10:00:00Z",
            }
        }
    )


class SessionListItem(BaseModel):
    session_id: int
    title: str | None = None
    status: str
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": 1001,
                "title": "프로젝트 생성 상담",
                "status": "active",
                "last_message_preview": "계획을 검토하고 승인하면 바로 실행합니다.",
                "last_message_at": "2026-04-02T10:01:02Z",
                "unread_count": 0,
            }
        }
    )


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]
    next_cursor: str | None = None
    has_more: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sessions": [
                    {
                        "session_id": 1001,
                        "title": "프로젝트 생성 상담",
                        "status": "active",
                        "last_message_preview": "계획을 검토하고 승인하면 바로 실행합니다.",
                        "last_message_at": "2026-04-02T10:01:02Z",
                        "unread_count": 0,
                    }
                ],
                "next_cursor": None,
                "has_more": False,
            }
        }
    )


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    messages: list[ConversationMessage]
    next_cursor: str | None = None
    has_more: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session": {
                    "session_id": 1001,
                    "user_id": "user-1",
                    "title": "프로젝트 생성 상담",
                    "status": "active",
                    "created_at": "2026-04-02T10:00:00Z",
                    "updated_at": "2026-04-02T10:01:02Z",
                },
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
                ],
                "next_cursor": None,
                "has_more": False,
            }
        }
    )
