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
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if start or end:
            params = {}
            if start:
                params["start"] = start
            if end:
                params["end"] = end
        response = await self.http_client.get(
            MonitoringAPIUrls.GET_APP_DEPLOYMENT_TRAFFIC.format(
                project_id=project_id,
                app_deployment_name=app_deployment_name,
            ),
            params=params,
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, app_deployment_name),
                "data": payload,
                "status_code": response.status,
            }

        traffic_data = self._extract_traffic_data(payload)
        return {
            "success": True,
            "summary": self._success_summary(app_deployment_name, traffic_data),
            "data": payload,
            "status_code": response.status,
        }

    def _headers(self, *, user_id: str, role: str | None) -> dict[str, str]:
        headers = {"X-User-Id": user_id}
        if role is not None:
            headers["X-User-Role"] = role
        return headers

    async def _read_payload(self, response) -> dict[str, Any] | list[Any] | str:
        try:
            return await response.json(content_type=None)
        except Exception:
            return await response.text()

    def _extract_traffic_data(self, payload: dict[str, Any] | list[Any] | str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return {}
        traffic = data.get("app_deployment_traffic", data)
        return traffic if isinstance(traffic, dict) else {}

    def _success_summary(self, app_deployment_name: str, traffic_data: dict[str, Any]) -> str:
        app_deployment = traffic_data.get("app_deployment", {})
        traffic = traffic_data.get("traffic", {})

        name = str(app_deployment.get("name") or app_deployment_name)
        details: list[str] = []

        cpu_usage = app_deployment.get("cpu_usage_percentage")
        if cpu_usage is not None:
            details.append(f"CPU {cpu_usage}%")

        current_instance = app_deployment.get("current_instance") or app_deployment.get("current_instances")
        available_instances = app_deployment.get("available_instances")
        if current_instance is not None and available_instances is not None:
            details.append(f"인스턴스 {current_instance}/{available_instances}")

        latest_traffic = None
        if isinstance(traffic, dict):
            series = traffic.get("series")
            if isinstance(series, list) and series:
                latest = series[-1]
                if isinstance(latest, dict) and latest.get("value") is not None:
                    latest_traffic = latest["value"]
        if latest_traffic is not None:
            details.append(f"최근 트래픽 {latest_traffic}")

        if not details:
            return f"{name} 앱 트래픽을 조회했습니다."
        return f"{name} 앱 트래픽을 조회했습니다. " + ", ".join(details)

    def _error_summary(self, status_code: int, app_deployment_name: str) -> str:
        if status_code in (401, 403):
            return f"{app_deployment_name} 앱 트래픽을 조회할 권한이 없습니다."
        if status_code == 404:
            return f"{app_deployment_name} 앱 트래픽을 찾을 수 없습니다."
        if status_code == 422:
            return f"{app_deployment_name} 앱 트래픽 조회 요청값이 올바르지 않습니다."
        if status_code >= 500:
            return "트래픽 조회 서비스가 일시적으로 응답하지 않습니다."
        return f"{app_deployment_name} 앱 트래픽을 조회하지 못했습니다."
