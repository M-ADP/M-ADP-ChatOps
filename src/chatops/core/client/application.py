from __future__ import annotations

from typing import Any, Protocol


class ApplicationClient(Protocol):
    async def create_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]: ...

    async def get_apps(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]: ...

    async def delete_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]: ...

    async def patch_apps_resources(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def patch_apps_github(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def get_apps_status(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]: ...

    async def get_apps_logs(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]: ...

    async def get_apps_details(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]: ...
