from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from chatops.services.registry import RegistryEntry


AsyncHandler = Callable[[str, str | None, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class DownstreamDispatcher:
    project_client: Any
    application_client: Any
    monitoring_client: Any

    async def execute_query(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del org_id
        handler = self._query_handler(operation.id)
        return await handler(user_id, user_role, resolved_inputs or {})

    async def execute_command(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del org_id
        handler = self._command_handler(operation.id)
        result = await handler(user_id, user_role, resolved_inputs or {})
        summary = result.get("summary", operation.id)
        return {
            "success": True,
            "summary": summary,
            "result": result,
        }

    def _query_handler(self, operation_id: str) -> AsyncHandler:
        handlers: dict[str, AsyncHandler] = {
            "project.list_projects": self._list_projects,
            "monitoring.get_app_deployment_traffic": self._get_app_deployment_traffic,
        }
        if operation_id not in handlers:
            raise ValueError(f"unsupported query operation: {operation_id}")
        return handlers[operation_id]

    def _command_handler(self, operation_id: str) -> AsyncHandler:
        handlers: dict[str, AsyncHandler] = {
            "project.create": self._create_project,
            "application.create_apps": self._create_apps,
        }
        if operation_id not in handlers:
            raise ValueError(f"unsupported command operation: {operation_id}")
        return handlers[operation_id]

    async def _create_project(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.project_client.create_project(
            user_id=user_id,
            role=user_role,
            body=resolved_inputs.get("body", {}),
        )

    async def _list_projects(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        del resolved_inputs
        return await self.project_client.list_projects(user_id=user_id, role=user_role)

    async def _create_apps(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.application_client.create_apps(
            user_id=user_id,
            role=user_role,
            body=resolved_inputs.get("body", {}),
        )

    async def _get_app_deployment_traffic(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        path_values = resolved_inputs.get("path", {})
        return await self.monitoring_client.get_app_deployment_traffic(
            user_id=user_id,
            role=user_role,
            project_id=path_values["project_id"],
            app_deployment_name=path_values["app_deployment_name"],
        )
