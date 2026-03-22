from __future__ import annotations

from typing import Any, Protocol


class ProjectClient(Protocol):
    async def create_project(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]: ...

    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, Any]: ...

