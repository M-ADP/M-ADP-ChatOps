from __future__ import annotations

from typing import Any, Protocol


class ApplicationClient(Protocol):
    async def create_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]: ...

