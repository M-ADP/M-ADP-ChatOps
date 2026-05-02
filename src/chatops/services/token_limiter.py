"""Redis 기반 사용자별 일일 토큰 사용량 제한.

키 형식: chatops:token:{user_id}:{YYYYMMDD}
TTL: 25시간 (UTC 기준 하루가 지나도 자동 만료)
모든 Redis 오류는 fail-open (서비스 중단 없이 한도 무시).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_KEY_PREFIX = "chatops:token"
_TTL_SECONDS = 25 * 3600  # 25h: 다음 날 0시 이후에도 이전 카운터가 남지 않도록 여유분


class RedisTokenLimiter:
    def __init__(self, client: Any, daily_limit: int = 1_000_000) -> None:
        self._client = client
        self.daily_limit = daily_limit

    def _key(self, user_id: str) -> str:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{_KEY_PREFIX}:{user_id}:{today}"

    def increment(self, user_id: str, tokens: int) -> int:
        """tokens만큼 누적하고 현재 일일 사용량을 반환. 실패 시 0 반환."""
        if tokens <= 0:
            return 0
        try:
            key = self._key(user_id)
            new_total = self._client.incrby(key, tokens)
            if int(new_total) == tokens:
                # 새로 생성된 키 — TTL 설정
                self._client.expire(key, _TTL_SECONDS)
            return int(new_total)
        except Exception:
            logger.warning("token_limiter.increment failed user_id=%s", user_id, exc_info=True)
            return 0

    def is_over_limit(self, user_id: str) -> bool:
        """일일 한도 초과 여부. Redis 오류 시 False (fail open)."""
        try:
            val = self._client.get(self._key(user_id))
            if val is None:
                return False
            return int(val) >= self.daily_limit
        except Exception:
            logger.warning("token_limiter.is_over_limit failed user_id=%s", user_id, exc_info=True)
            return False

    def get_daily_usage(self, user_id: str) -> int:
        """현재 일일 누적 사용량. 오류 시 0 반환."""
        try:
            val = self._client.get(self._key(user_id))
            return int(val) if val is not None else 0
        except Exception:
            logger.warning("token_limiter.get_daily_usage failed user_id=%s", user_id, exc_info=True)
            return 0
