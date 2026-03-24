from __future__ import annotations

from enum import Enum
from typing import Any

from chatops.common.config.application_server import ApplicationServerConfig
from chatops.core.client.http import HttpClient
from chatops.infra.client.asyncio_http import AioHttpClient


class ApplicationAPIUrls(str, Enum):
    CREATE_APPS = "/apps"
    GET_APPS = "/apps"
    DELETE_APPS = "/apps"
    PATCH_APPS_RESOURCES = "/apps/resources"
    PATCH_APPS_GITHUB = "/apps/github"
    GET_APPS_LOGS = "/apps/logs"
    GET_APPS_STATUS = "/apps/status"
    GET_APPS_DETAILS = "/apps/details"


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
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        return {
            "success": True,
            "summary": "application.create_apps",
            "data": payload,
            "status_code": response.status,
        }

    async def get_apps(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]:
        response = await self.http_client.get(
            ApplicationAPIUrls.GET_APPS,
            params={"project_id": project_id},
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        items = self._extract_items(payload)
        if not items:
            return {"summary": "애플리케이션 목록이 없습니다.", "items": []}
        summary = ", ".join(str(item.get("name", "unknown")) for item in items if isinstance(item, dict))
        return {"summary": summary, "items": items}

    async def delete_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        response = await self.http_client.delete(
            ApplicationAPIUrls.DELETE_APPS,
            json=body,
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        return {
            "success": True,
            "summary": "application.delete_apps",
            "data": payload,
            "status_code": response.status,
        }

    async def patch_apps_resources(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.http_client.patch(
            ApplicationAPIUrls.PATCH_APPS_RESOURCES,
            json=body,
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        return {
            "success": True,
            "summary": "application.patch_apps_resources",
            "data": payload,
            "status_code": response.status,
        }

    async def patch_apps_github(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.http_client.patch(
            ApplicationAPIUrls.PATCH_APPS_GITHUB,
            json=body,
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        return {
            "success": True,
            "summary": "application.patch_apps_github",
            "data": payload,
            "status_code": response.status,
        }

    async def get_apps_status(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            ApplicationAPIUrls.GET_APPS_STATUS,
            params={"project_id": project_id, "app_name": app_name},
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        app_id = data.get("appId") if isinstance(data, dict) else None
        return {
            "success": True,
            "summary": (
                f"{app_name} 앱 상태: CPU {data.get('cpu_usage_percentage')}%, "
                f"인스턴스 {data.get('current_instances')}/{data.get('available_instances')}"
            ),
            "data": payload,
            "app_id": app_id,
            "status_code": response.status,
        }

    async def get_apps_logs(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            ApplicationAPIUrls.GET_APPS_LOGS,
            params={"project_id": project_id, "app_name": app_name},
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        data = payload.get("data", "") if isinstance(payload, dict) else payload
        return {"summary": f"{app_name} 앱 로그", "data": data}

    async def get_apps_details(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            ApplicationAPIUrls.GET_APPS_DETAILS,
            params={"project_id": project_id, "app_name": app_name},
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_payload(response)
        if response.status >= 400:
            return self._error_result(response.status, payload)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        summary = (
            f"{app_name} 앱 상세: 포트 {data.get('port')}, 상태 {data.get('status')}"
            if isinstance(data, dict)
            else f"{app_name} 앱 상세"
        )
        return {"summary": summary, "data": data}

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

    def _extract_items(self, payload: dict[str, Any] | list[Any] | str) -> list[Any]:
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, list):
                return data
        elif isinstance(payload, list):
            return payload
        return []

    def _error_result(self, status_code: int, payload: dict[str, Any] | list[Any] | str) -> dict[str, Any]:
        return {
            "success": False,
            "summary": self._error_summary(status_code, payload),
            "data": payload,
            "status_code": status_code,
        }

    def _error_summary(self, status_code: int, payload: dict[str, Any] | list[Any] | str) -> str:
        if status_code in {400, 422}:
            return "요청값이 올바르지 않습니다."
        if status_code in {401, 403}:
            return "실행 권한이 없습니다."
        if status_code == 404:
            return "대상 리소스를 찾지 못했습니다."
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
        return "애플리케이션 명령 실행에 실패했습니다."
