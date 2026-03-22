from __future__ import annotations

from typing import Any


class FakeProjectClientImpl:
    async def create_project(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        del user_id, role, body
        return {"summary": "project.create"}

    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, Any]:
        del user_id, role
        return {"summary": "프로젝트 목록이 없습니다.", "items": []}

