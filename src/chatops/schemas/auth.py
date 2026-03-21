from __future__ import annotations

from pydantic import BaseModel


class AuthContext(BaseModel):
    user_id: str
    request_id: str | None = None
    user_role: str | None = None
    org_id: str | None = None
