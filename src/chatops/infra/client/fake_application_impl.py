from __future__ import annotations

from typing import Any


class FakeApplicationClientImpl:
    async def create_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        del user_id, role, body
        return {"summary": "application.create_apps"}

