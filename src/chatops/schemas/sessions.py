from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    title: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
