from __future__ import annotations

from enum import Enum
from typing import Any

from chatops.common.config.monitoring_server import MonitoringServerConfig
from chatops.core.client.http import HttpClient
from chatops.infra.client.asyncio_http import AioHttpClient


class MonitoringAPIUrls(str, Enum):
    GET_APP_DEPLOYMENT_TRAFFIC = "/monitoring/app-deployment/{project_id}/{app_deployment_name}"


class MonitoringClientImpl:
    def __init__(
        self,
        config: MonitoringServerConfig,
        http_client: HttpClient | None = None,
    ) -> None:
        self.http_client = http_client or AioHttpClient(base_url=config.SERVER_BASE_URL)

    async def get_app_deployment_traffic(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_deployment_name: str,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            MonitoringAPIUrls.GET_APP_DEPLOYMENT_TRAFFIC.format(
                project_id=project_id,
                app_deployment_name=app_deployment_name,
            ),
            headers=self._headers(user_id=user_id, role=role),
        )
        try:
            payload = await response.json(content_type=None)
        except Exception:
            payload = await response.text()
        return {
            "summary": "monitoring.get_app_deployment_traffic",
            "data": payload,
            "status_code": response.status,
        }

    def _headers(self, *, user_id: str, role: str | None) -> dict[str, str]:
        headers = {"X-User-Id": user_id}
        if role is not None:
            headers["X-User-Role"] = role
        return headers
