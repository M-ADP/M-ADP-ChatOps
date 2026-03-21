from __future__ import annotations

from fastapi import HTTPException, status

from chatops.schemas.auth import AuthContext


def build_auth_context(
    user_id: str | None,
    request_id: str | None = None,
    user_role: str | None = None,
    org_id: str | None = None,
) -> AuthContext:
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header is required",
        )

    return AuthContext(
        user_id=user_id,
        request_id=request_id,
        user_role=user_role,
        org_id=org_id,
    )
