from __future__ import annotations

from enum import Enum
from typing import Any

from chatops.common.config.project_server import ProjectServerConfig
from chatops.core.client.http import HttpClient
from chatops.infra.client.asyncio_http import AioHttpClient


class ProjectAPIUrls(str, Enum):
    CREATE_PROJECT = "/projects"
    LIST_PROJECTS = "/projects"


class ProjectClientImpl:
    def __init__(
        self,
        config: ProjectServerConfig,
        http_client: HttpClient | None = None,
    ) -> None:
        self.http_client = http_client or AioHttpClient(base_url=config.SERVER_BASE_URL)

    async def create_project(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        response = await self.http_client.post(
            ProjectAPIUrls.CREATE_PROJECT,
            json=body,
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_json(response)
        return {
            "summary": "project.create",
            "data": payload,
            "status_code": response.status,
        }

    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, Any]:
        response = await self.http_client.get(
            ProjectAPIUrls.LIST_PROJECTS,
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_json(response)
        items = payload.get("data", []) if isinstance(payload, dict) else payload
        if not items:
            return {"summary": "프로젝트 목록이 없습니다.", "items": []}
        project_names = [str(item.get("name", item.get("id"))) for item in items if isinstance(item, dict)]
        return {
            "summary": ", ".join(project_names),
            "items": items,
        }

    def _headers(self, *, user_id: str, role: str | None) -> dict[str, str]:
        headers = {"X-User-Id": user_id}
        if role is not None:
            headers["X-User-Role"] = role
        return headers

    async def _read_json(self, response) -> dict[str, Any] | list[Any] | str:
        try:
            return await response.json(content_type=None)
        except Exception:
            return await response.text()

