from __future__ import annotations

from pydantic import BaseModel


class AuthContext(BaseModel):
    user_id: str
    user_role: str | None = None
