from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateRequestRequest(BaseModel):
    message: str


class RequestResponse(BaseModel):
    request_id: str
    session_id: str
    status: str
    message: str
    request_type: str | None = None
    requires_approval: bool = False
    final_response: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApproveRequestResponse(BaseModel):
    request_id: str
    status: str


class RejectRequestResponse(BaseModel):
    request_id: str
    status: str
