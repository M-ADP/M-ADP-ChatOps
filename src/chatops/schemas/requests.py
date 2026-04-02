from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateRequestRequest(BaseModel):
    message: str


class ApproveRequestRequest(BaseModel):
    confirmation_text: str | None = None


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
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApproveRequestResponse(BaseModel):
    request_id: int
    status: str
    assistant_message: str | None = None


class RejectRequestResponse(BaseModel):
    request_id: int
    status: str
    assistant_message: str | None = None
