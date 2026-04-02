from __future__ import annotations

from fastapi import HTTPException, status

from chatops.schemas.auth import AuthContext


def build_auth_context(
    user_id: str | None,
    user_role: str | None = None,
) -> AuthContext:
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header is required",
        )

    return AuthContext(
        user_id=user_id,
        user_role=user_role,
    )


def missing_auth_headers(
    required_headers: tuple[str, ...] | list[str],
    *,
    user_id: str | None,
    user_role: str | None = None,
) -> list[str]:
    header_values = {
        "X-User-Id": user_id,
        "X-User-Role": user_role,
    }
    missing: list[str] = []
    for header in required_headers:
        if not header_values.get(header):
            missing.append(header)
    return missing


def format_missing_auth_headers(missing_headers: list[str]) -> str:
    if not missing_headers:
        return "인증 정보를 확인할 수 없습니다."

    if len(missing_headers) == 1:
        return (
            f"현재 요청을 처리하려면 {missing_headers[0]} 헤더가 필요합니다. "
            "호출 컨텍스트를 확인한 뒤 다시 시도해주세요."
        )

    joined = ", ".join(missing_headers)
    return (
        f"현재 요청을 처리하려면 다음 헤더가 필요합니다: {joined}. "
        "호출 컨텍스트를 확인한 뒤 다시 시도해주세요."
    )
