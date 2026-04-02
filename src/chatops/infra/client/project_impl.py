from __future__ import annotations

from enum import Enum
from typing import Any

from chatops.common.config.project_server import ProjectServerConfig
from chatops.core.client.http import HttpClient
from chatops.infra.client.asyncio_http import AioHttpClient


class ProjectAPIUrls(str, Enum):
    CREATE_PROJECT = "/projects"
    LIST_PROJECTS = "/projects"
    GET_PROJECT = "/projects/{project_id}"
    GET_PROJECT_RESOURCE_LIMIT = "/projects/resource-limit"
    CHECK_PROJECT_AVAILABLE = "/projects/available"
    CHECK_PROJECT_OWNER = "/projects/owner"
    LIST_PROJECT_MEMBERS = "/projects/{project_id}/members"
    ADD_PROJECT_MEMBER = "/projects/{project_id}/members"
    REMOVE_PROJECT_MEMBER = "/projects/{project_id}/members/{target_user_id}"
    TRANSFER_PROJECT_OWNERSHIP = "/projects/{project_id}/owner"
    UPDATE_PROJECT_NAME = "/projects/{project_id}/name"
    UPDATE_PROJECT_RESOURCE = "/projects/{project_id}/resource"
    DELETE_PROJECT = "/projects/{project_id}"


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
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        return {
            "success": True,
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
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        items = self._extract_items(payload)
        if not items:
            return {"summary": "프로젝트 목록이 없습니다.", "items": []}
        project_names = [str(item.get("name", item.get("id"))) for item in items if isinstance(item, dict)]
        return {
            "summary": ", ".join(project_names),
            "items": items,
            "status_code": response.status,
        }

    async def get_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]:
        response = await self.http_client.get(
            ProjectAPIUrls.GET_PROJECT.value.format(project_id=project_id),
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_json(response)
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        data = self._extract_data(payload)
        name = data.get("name", project_id) if isinstance(data, dict) else project_id
        deployments = len(data.get("deployments", [])) if isinstance(data, dict) else 0
        my_role = data.get("my_role") if isinstance(data, dict) else None
        summary = f"{name} 프로젝트 상세"
        if my_role:
            summary += f" (역할: {my_role})"
        summary += f", 배포 {deployments}개"
        return {"summary": summary, "data": data}

    async def get_project_resource_limit(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            ProjectAPIUrls.GET_PROJECT_RESOURCE_LIMIT,
            params={"project_id": project_id},
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_json(response)
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        data = self._extract_data(payload)
        summary = (
            f"프로젝트 리소스 한도: CPU {data.get('max_cpu')}, "
            f"메모리 {data.get('max_memory')}GB, 디스크 {data.get('max_disk')}GB"
            if isinstance(data, dict)
            else "프로젝트 리소스 한도를 조회했습니다."
        )
        return {"summary": summary, "data": data}

    async def check_project_available(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            ProjectAPIUrls.CHECK_PROJECT_AVAILABLE,
            params={"project_id": project_id},
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_json(response)
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        data = self._extract_data(payload)
        status = bool(data.get("status")) if isinstance(data, dict) else False
        return {
            "summary": "프로젝트에 접근 가능합니다." if status else "프로젝트에 접근할 수 없습니다.",
            "data": data,
        }

    async def check_project_owner(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            ProjectAPIUrls.CHECK_PROJECT_OWNER,
            params={"project_id": project_id},
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_json(response)
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        data = self._extract_data(payload)
        status = bool(data.get("status")) if isinstance(data, dict) else False
        return {
            "summary": "프로젝트 소유자입니다." if status else "프로젝트 소유자가 아닙니다.",
            "data": data,
        }

    async def list_project_members(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        response = await self.http_client.get(
            ProjectAPIUrls.LIST_PROJECT_MEMBERS.value.format(project_id=project_id),
            headers=self._headers(user_id=user_id, role=role),
        )
        payload = await self._read_json(response)
        if response.status >= 400:
            return {
                "success": False,
                "summary": self._error_summary(response.status, payload),
                "data": payload,
                "status_code": response.status,
            }
        items = self._extract_items(payload)
        if not items:
            return {"summary": "프로젝트 멤버가 없습니다.", "items": []}
        summary = ", ".join(
            f"{item.get('username', item.get('user_id'))}({item.get('role', '')})"
            for item in items
            if isinstance(item, dict)
        )
        return {"summary": summary, "items": items}

    async def add_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.http_client.post(
            ProjectAPIUrls.ADD_PROJECT_MEMBER.value.format(project_id=project_id),
            json=body,
            headers=self._headers(user_id=user_id, role=role),
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
            "summary": "project.add_member",
            "data": payload,
            "status_code": response.status,
        }

    async def remove_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        target_user_id: int,
    ) -> dict[str, Any]:
        response = await self.http_client.delete(
            ProjectAPIUrls.REMOVE_PROJECT_MEMBER.value.format(project_id=project_id, target_user_id=target_user_id),
            headers=self._headers(user_id=user_id, role=role),
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
            "summary": "project.remove_member",
            "data": payload,
            "status_code": response.status,
        }

    async def transfer_project_ownership(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.http_client.patch(
            ProjectAPIUrls.TRANSFER_PROJECT_OWNERSHIP.value.format(project_id=project_id),
            json=body,
            headers=self._headers(user_id=user_id, role=role),
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
            "summary": "project.transfer_ownership",
            "data": payload,
            "status_code": response.status,
        }

    async def update_project_name(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.http_client.patch(
            ProjectAPIUrls.UPDATE_PROJECT_NAME.value.format(project_id=project_id),
            json=body,
            headers=self._headers(user_id=user_id, role=role),
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
            "summary": "project.update_name",
            "data": payload,
            "status_code": response.status,
        }

    async def update_project_resource(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.http_client.patch(
            ProjectAPIUrls.UPDATE_PROJECT_RESOURCE.value.format(project_id=project_id),
            json=body,
            headers=self._headers(user_id=user_id, role=role),
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
            "summary": "project.update_resource",
            "data": payload,
            "status_code": response.status,
        }

    async def delete_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]:
        response = await self.http_client.delete(
            ProjectAPIUrls.DELETE_PROJECT.value.format(project_id=project_id),
            headers=self._headers(user_id=user_id, role=role),
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
            "summary": "project.delete",
            "data": payload,
            "status_code": response.status,
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

    def _extract_data(self, payload: dict[str, Any] | list[Any] | str) -> dict[str, Any] | list[Any] | str:
        if isinstance(payload, dict):
            return payload.get("data", payload)
        return payload

    def _extract_items(self, payload: dict[str, Any] | list[Any] | str) -> list[Any]:
        data = self._extract_data(payload)
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return items
            return []
        if isinstance(data, list):
            return data
        return []

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
        return "프로젝트 명령 실행에 실패했습니다."
