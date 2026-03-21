from fastapi import Header

from chatops.config import Settings, get_settings
from chatops.schemas.auth import AuthContext
from chatops.services.auth import build_auth_context


def get_app_settings() -> Settings:
    return get_settings()


def get_auth_context(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
) -> AuthContext:
    return build_auth_context(
        user_id=x_user_id,
        request_id=x_request_id,
        user_role=x_user_role,
        org_id=x_org_id,
    )
