from __future__ import annotations

from typing import Any, Protocol


class ProjectClient(Protocol):
    async def create_project(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]: ...

    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, Any]: ...

    async def get_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]: ...

    async def get_project_resource_limit(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]: ...

    async def check_project_available(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]: ...

    async def check_project_owner(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]: ...

    async def list_project_members(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]: ...

    async def add_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def remove_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        target_user_id: int,
    ) -> dict[str, Any]: ...

    async def transfer_project_ownership(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def update_project_name(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def update_project_resource(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def delete_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]: ...
