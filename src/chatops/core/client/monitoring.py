from __future__ import annotations

from typing import Any, Protocol


class MonitoringClient(Protocol):
    async def get_app_deployment_traffic(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_deployment_name: str,
    ) -> dict[str, Any]: ...

