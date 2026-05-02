from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from chatops.api.dependencies import get_auth_context, get_token_limiter
from chatops.common.config.settings import get_token_limit_config
from chatops.schemas.auth import AuthContext

router = APIRouter(prefix="/usage", tags=["usage"])


class TokenUsageResponse(BaseModel):
    daily_usage: int
    daily_limit: int
    resets_at: datetime


@router.get("/tokens", response_model=TokenUsageResponse)
def get_token_usage(
    auth: AuthContext = Depends(get_auth_context),
) -> TokenUsageResponse:
    """사용자의 오늘 토큰 사용량과 일일 한도를 반환한다."""
    daily_limit = get_token_limit_config().token_daily_limit
    token_limiter = get_token_limiter()
    daily_usage = token_limiter.get_daily_usage(auth.user_id) if token_limiter is not None else 0

    now = datetime.now(timezone.utc)
    resets_at = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return TokenUsageResponse(
        daily_usage=daily_usage,
        daily_limit=daily_limit,
        resets_at=resets_at,
    )
