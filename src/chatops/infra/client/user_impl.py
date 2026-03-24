from __future__ import annotations

from enum import Enum
from typing import Any

from chatops.common.config.user_server import UserServerConfig
from chatops.core.client.http import HttpClient
from chatops.infra.client.asyncio_http import AioHttpClient


class UserAPIUrls(str, Enum):
    GET_PROFILE_BY_NICKNAME = "/user/profile/{nickname}"


class UserClientImpl:
    def __init__(
        self,
        config: UserServerConfig,
        http_client: HttpClient | None = None,
    ) -> None:
        self.http_client = http_client or AioHttpClient(base_url=config.SERVER_BASE_URL)

    async def get_profile_by_nickname(self, *, nickname: str) -> dict[str, object]:
        response = await self.http_client.get(
            UserAPIUrls.GET_PROFILE_BY_NICKNAME.value.format(nickname=nickname),
        )
        payload = await self._read_json(response)
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        return {
            "success": True,
            "summary": "user.get_profile_by_nickname",
            "data": payload,
            "status_code": response.status,
        }

    async def _read_json(self, response) -> dict[str, Any] | list[Any] | str:
        try:
            return await response.json(content_type=None)
        except Exception:
            return await response.text()

    def _error_summary(self, status_code: int, payload: dict[str, Any] | list[Any] | str) -> str:
        if status_code == 404:
            return "대상 사용자를 찾지 못했습니다."
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
        return "사용자 조회에 실패했습니다."
