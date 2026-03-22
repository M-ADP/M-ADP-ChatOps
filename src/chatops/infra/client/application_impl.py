from __future__ import annotations

from enum import Enum
from typing import Any

from chatops.common.config.application_server import ApplicationServerConfig
from chatops.core.client.http import HttpClient
from chatops.infra.client.asyncio_http import AioHttpClient


class ApplicationAPIUrls(str, Enum):
    CREATE_APPS = "/apps"


class ApplicationClientImpl:
    def __init__(
        self,
        config: ApplicationServerConfig,
        http_client: HttpClient | None = None,
    ) -> None:
        self.http_client = http_client or AioHttpClient(base_url=config.SERVER_BASE_URL)

    async def create_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        response = await self.http_client.post(
            ApplicationAPIUrls.CREATE_APPS,
            json=body,
            headers=self._headers(user_id=user_id, role=role),
        )
        try:
            payload = await response.json(content_type=None)
        except Exception:
            payload = await response.text()
        return {
            "summary": "application.create_apps",
            "data": payload,
            "status_code": response.status,
        }

    def _headers(self, *, user_id: str, role: str | None) -> dict[str, str]:
        headers = {"X-User-Id": user_id}
        if role is not None:
            headers["X-User-Role"] = role
        return headers

