from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from chatops.services.name_matcher import match_name
from chatops.services.registry import RegistryEntry
from chatops.services.user_matcher import match_user


AsyncHandler = Callable[[str, str | None, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class DownstreamDispatcher:
    project_client: Any
    application_client: Any
    monitoring_client: Any
    user_client: Any | None = None

    async def execute_query(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del org_id
        resolved_inputs = resolved_inputs or {}
        handler = self._query_handler(operation.id)
        try:
            result = await handler(user_id, user_role, resolved_inputs)
        except EntityResolutionError as exc:
            return {
                "success": False,
                "summary": exc.summary,
                "status_code": 404,
                "fallback_used": self._fallback_used(resolved_inputs),
            }
        fallback_used = bool(result.get("fallback_used", False) or self._fallback_used(resolved_inputs))
        if result.get("success") is False:
            if fallback_used and "fallback_used" not in result:
                return {**result, "fallback_used": True}
            return result
        if int(result.get("status_code", 200)) >= 400:
            return {
                "success": False,
                "summary": str(result.get("summary", operation.id)),
                "status_code": int(result.get("status_code", 500)),
                "fallback_used": fallback_used,
            }
        if fallback_used:
            return {**result, "fallback_used": True}
        return result

    async def execute_command(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del org_id
        resolved_inputs = resolved_inputs or {}
        handler = self._command_handler(operation.id)
        try:
            result = await handler(user_id, user_role, resolved_inputs)
        except EntityResolutionError as exc:
            return {
                "success": False,
                "summary": exc.summary,
                "status_code": 404,
                "fallback_used": self._fallback_used(resolved_inputs),
            }
        fallback_used = bool(result.get("fallback_used", False) or self._fallback_used(resolved_inputs))
        if result.get("success") is False:
            if fallback_used and "fallback_used" not in result:
                return {**result, "fallback_used": True}
            return result
        if int(result.get("status_code", 200)) >= 400:
            return {
                "success": False,
                "summary": str(result.get("summary", operation.id)),
                "status_code": int(result.get("status_code", 500)),
                "fallback_used": fallback_used,
            }
        summary = result.get("summary", operation.id)
        response = {
            "success": True,
            "summary": summary,
            "result": result,
        }
        if fallback_used:
            response["fallback_used"] = True
        return response

    def _query_handler(self, operation_id: str) -> AsyncHandler:
        handlers: dict[str, AsyncHandler] = {
            "project.list_projects": self._list_projects,
            "project.get": self._get_project,
            "project.get_resource_limit": self._get_project_resource_limit,
            "project.check_available": self._check_project_available,
            "project.check_owner": self._check_project_owner,
            "project.list_members": self._list_project_members,
            "application.get_apps": self._get_apps,
            "application.get_apps_status": self._get_apps_status,
            "application.get_apps_logs": self._get_apps_logs,
            "application.get_apps_details": self._get_apps_details,
            "monitoring.get_app_deployment_traffic": self._get_app_deployment_traffic,
        }
        if operation_id not in handlers:
            raise ValueError(f"unsupported query operation: {operation_id}")
        return handlers[operation_id]

    def _command_handler(self, operation_id: str) -> AsyncHandler:
        handlers: dict[str, AsyncHandler] = {
            "project.create": self._create_project,
            "project.update_name": self._update_project_name,
            "project.update_resource": self._update_project_resource,
            "project.delete": self._delete_project,
            "project.add_member": self._add_project_member,
            "project.remove_member": self._remove_project_member,
            "project.transfer_ownership": self._transfer_project_ownership,
            "application.create_apps": self._create_apps,
            "application.delete_apps": self._delete_apps,
            "application.patch_apps_resources": self._patch_apps_resources,
            "application.patch_apps_github": self._patch_apps_github,
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

    async def _get_project(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.get_project(user_id=user_id, role=user_role, project_id=project_id)

    async def _get_project_resource_limit(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.get_project_resource_limit(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )

    async def _check_project_available(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.check_project_available(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )

    async def _check_project_owner(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.check_project_owner(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )

    async def _list_project_members(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.list_project_members(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )

    async def _update_project_name(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.update_project_name(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            body=resolved_inputs.get("body", {}),
        )

    async def _delete_project(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.delete_project(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )

    async def _update_project_resource(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.update_project_resource(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            body=resolved_inputs.get("body", {}),
        )

    async def _add_project_member(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        target_user_id = await self._resolve_target_user_id(
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.add_project_member(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            body={"user_id": target_user_id},
        )

    async def _remove_project_member(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        target_user_id = await self._resolve_target_user_id(
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.remove_project_member(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            target_user_id=target_user_id,
        )

    async def _transfer_project_ownership(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        target_user_id = await self._resolve_target_user_id(
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            resolved_inputs=resolved_inputs,
        )
        return await self.project_client.transfer_project_ownership(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            body={"target_user_id": target_user_id},
        )

    async def _create_apps(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        body = dict(resolved_inputs.get("body", {}))
        body["project_id"] = project_id
        return await self.application_client.create_apps(
            user_id=user_id,
            role=user_role,
            body=body,
        )

    async def _get_apps(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.application_client.get_apps(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )

    async def _delete_apps(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        application_id = await self._resolve_application_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        return await self.application_client.delete_apps(
            user_id=user_id,
            role=user_role,
            body={"application_id": application_id},
        )

    async def _patch_apps_resources(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        application_id = await self._resolve_application_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        body = dict(resolved_inputs.get("body", {}))
        body["application_id"] = application_id
        return await self.application_client.patch_apps_resources(
            user_id=user_id,
            role=user_role,
            body=body,
        )

    async def _patch_apps_github(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        application_id = await self._resolve_application_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        body = dict(resolved_inputs.get("body", {}))
        body["appDeploymentId"] = application_id
        return await self.application_client.patch_apps_github(
            user_id=user_id,
            role=user_role,
            body=body,
        )

    async def _get_app_deployment_traffic(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        path_values = resolved_inputs.get("path", {})
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        application_name = (
            path_values.get("app_deployment_name")
            or resolved_inputs.get("references", {}).get("application_name")
        )
        query_values = resolved_inputs.get("query", {})
        if not application_name:
            raise EntityResolutionError("대상 앱 이름을 찾지 못했습니다.")
        monitoring_kwargs: dict[str, Any] = {}
        if query_values.get("start"):
            monitoring_kwargs["start"] = str(query_values["start"])
        if query_values.get("end"):
            monitoring_kwargs["end"] = str(query_values["end"])
        return await self.monitoring_client.get_app_deployment_traffic(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            app_deployment_name=str(application_name),
            **monitoring_kwargs,
        )

    async def _get_apps_status(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        application_name = resolved_inputs.get("references", {}).get("application_name")
        if not application_name:
            raise EntityResolutionError("대상 앱을 찾지 못했습니다.")
        result = await self.application_client.get_apps_status(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            app_name=str(application_name),
        )
        return await self._apply_application_query_fallback(
            result=result,
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            application_name=str(application_name),
        )

    async def _get_apps_logs(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        application_name = resolved_inputs.get("references", {}).get("application_name")
        if not application_name:
            raise EntityResolutionError("대상 앱을 찾지 못했습니다.")
        result = await self.application_client.get_apps_logs(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            app_name=str(application_name),
        )
        return await self._apply_application_query_fallback(
            result=result,
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            application_name=str(application_name),
        )

    async def _get_apps_details(
        self,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        application_name = resolved_inputs.get("references", {}).get("application_name")
        if not application_name:
            raise EntityResolutionError("대상 앱을 찾지 못했습니다.")
        result = await self.application_client.get_apps_details(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            app_name=str(application_name),
        )
        return await self._apply_application_query_fallback(
            result=result,
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            application_name=str(application_name),
        )

    async def _resolve_project_id(
        self,
        *,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> int:
        resolved_ids = resolved_inputs.get("resolved_ids", {})
        if "project_id" in resolved_ids:
            return int(resolved_ids["project_id"])
        path_values = resolved_inputs.get("path", {})
        if "project_id" in path_values:
            return int(path_values["project_id"])

        body_values = resolved_inputs.get("body", {})
        if "project_id" in body_values:
            return int(body_values["project_id"])

        project_name = resolved_inputs.get("references", {}).get("project_name")
        if not project_name:
            raise EntityResolutionError("대상 프로젝트를 찾지 못했습니다.")

        projects = await self.project_client.list_projects(user_id=user_id, role=user_role)
        if projects.get("success") is False:
            raise EntityResolutionError(str(projects.get("summary", "프로젝트 목록을 조회하지 못했습니다.")))
        items = projects.get("items", [])
        names_by_value: dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("name") is not None and item.get("id") is not None:
                names_by_value[str(item["name"])] = int(item["id"])
        matched = match_name(str(project_name), list(names_by_value.keys()))
        if matched.matched_name is not None:
            return names_by_value[matched.matched_name]
        message = f"프로젝트 '{project_name}'을(를) 찾지 못했습니다."
        if matched.suggestions:
            message += "\n비슷한 프로젝트: " + ", ".join(matched.suggestions)
        raise EntityResolutionError(message)

    async def _resolve_application_id(
        self,
        *,
        user_id: str,
        user_role: str | None,
        resolved_inputs: dict[str, Any],
    ) -> int:
        resolved_ids = resolved_inputs.get("resolved_ids", {})
        if "application_id" in resolved_ids:
            return int(resolved_ids["application_id"])
        body_values = resolved_inputs.get("body", {})
        if "application_id" in body_values:
            return int(body_values["application_id"])
        if "appDeploymentId" in body_values:
            return int(body_values["appDeploymentId"])

        application_name = resolved_inputs.get("references", {}).get("application_name")
        if not application_name:
            raise EntityResolutionError("대상 앱을 찾지 못했습니다.")

        project_id = await self._resolve_project_id(
            user_id=user_id,
            user_role=user_role,
            resolved_inputs=resolved_inputs,
        )
        status = await self.application_client.get_apps_status(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            app_name=str(application_name),
        )
        if status.get("success") is False:
            if int(status.get("status_code", 0)) == 404:
                self._mark_fallback_used(resolved_inputs)
                return await self._resolve_application_id_from_list(
                    user_id=user_id,
                    user_role=user_role,
                    project_id=project_id,
                    application_name=str(application_name),
                )
            raise EntityResolutionError(str(status.get("summary", "대상 앱을 찾지 못했습니다.")))

        app_id = status.get("app_id")
        if app_id is None and isinstance(status.get("data"), dict):
            data = status["data"]
            app_id = data.get("appId") or data.get("app_id")
        if app_id is None:
            self._mark_fallback_used(resolved_inputs)
            return await self._resolve_application_id_from_list(
                user_id=user_id,
                user_role=user_role,
                project_id=project_id,
                application_name=str(application_name),
            )
        return int(app_id)

    async def _resolve_target_user_id(
        self,
        *,
        user_id: str,
        user_role: str | None,
        project_id: int,
        resolved_inputs: dict[str, Any],
    ) -> int:
        resolved_ids = resolved_inputs.get("resolved_ids", {})
        if "target_user_id" in resolved_ids:
            return int(resolved_ids["target_user_id"])
        references = resolved_inputs.get("references", {})
        nickname = references.get("target_nickname")
        if not nickname:
            body_values = resolved_inputs.get("body", {})
            if "user_id" in body_values:
                return int(body_values["user_id"])
            if "target_user_id" in body_values:
                return int(body_values["target_user_id"])
            raise EntityResolutionError("대상 사용자를 찾지 못했습니다.")
        suggestions: list[str] = []
        if hasattr(self.project_client, "list_project_members"):
            members = await self.project_client.list_project_members(
                user_id=user_id,
                role=user_role,
                project_id=project_id,
            )
            if members.get("success") is not False:
                matched = match_user(str(nickname), members.get("items", []))
                if matched.user_id is not None:
                    return matched.user_id
                suggestions = matched.suggestions
        if self.user_client is None:
            raise EntityResolutionError("대상 사용자를 찾을 수 없습니다.")
        profile = await self.user_client.get_profile_by_nickname(nickname=str(nickname))
        if profile.get("success") is False:
            raise EntityResolutionError(self._user_not_found_message(str(nickname), suggestions))
        data = profile.get("data")
        if not isinstance(data, dict) or data.get("id") is None:
            raise EntityResolutionError(self._user_not_found_message(str(nickname), suggestions))
        return int(data["id"])

    async def _resolve_application_id_from_list(
        self,
        *,
        user_id: str,
        user_role: str | None,
        project_id: int,
        application_name: str,
    ) -> int:
        apps = await self.application_client.get_apps(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )
        if apps.get("success") is False:
            raise EntityResolutionError(str(apps.get("summary", "앱 목록을 조회하지 못했습니다.")))
        items = apps.get("items", [])
        names_by_value: dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            application_id = item.get("id") or item.get("appId") or item.get("app_id")
            if name is not None and application_id is not None:
                names_by_value[str(name)] = int(application_id)
        matched = match_name(application_name, list(names_by_value.keys()))
        if matched.matched_name is not None:
            return names_by_value[matched.matched_name]
        message = f"앱 '{application_name}'을(를) 찾지 못했습니다."
        if matched.suggestions:
            message += "\n비슷한 앱: " + ", ".join(matched.suggestions)
        raise EntityResolutionError(message)

    async def _apply_application_query_fallback(
        self,
        *,
        result: dict[str, Any],
        user_id: str,
        user_role: str | None,
        project_id: int,
        application_name: str,
    ) -> dict[str, Any]:
        if result.get("success") is not False or int(result.get("status_code", 0)) != 404:
            return result
        suggestions = await self._get_application_suggestions(
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            application_name=application_name,
        )
        if not suggestions:
            return {**result, "fallback_used": True}
        summary = str(result.get("summary", "대상 리소스를 찾지 못했습니다."))
        return {
            **result,
            "summary": f"{summary}\n비슷한 앱: {', '.join(suggestions)}",
            "fallback_used": True,
        }

    async def _get_application_suggestions(
        self,
        *,
        user_id: str,
        user_role: str | None,
        project_id: int,
        application_name: str,
    ) -> list[str]:
        apps = await self.application_client.get_apps(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
        )
        if apps.get("success") is False:
            return []
        items = apps.get("items", [])
        available_names = [str(item.get("name", "")) for item in items if isinstance(item, dict) and item.get("name") is not None]
        return match_name(application_name, available_names).suggestions

    @staticmethod
    def _find_similar_names(target: str, names: list[str], limit: int = 3) -> list[str]:
        target_lower = target.lower()
        scored: list[tuple[str, int]] = []
        for name in names:
            name_lower = name.lower()
            if target_lower in name_lower or name_lower in target_lower:
                scored.append((name, 2))
                continue
            common = sum(1 for char in target_lower if char.isalnum() and char in name_lower)
            if common:
                scored.append((name, common))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [name for name, _score in scored[:limit]]

    @staticmethod
    def _user_not_found_message(nickname: str, suggestions: list[str]) -> str:
        message = f"사용자 '{nickname}'을(를) 찾지 못했습니다."
        if suggestions:
            message += "\n비슷한 사용자: " + ", ".join(suggestions)
        return message

    @staticmethod
    def _mark_fallback_used(resolved_inputs: dict[str, Any]) -> None:
        audit = resolved_inputs.setdefault("audit", {})
        if isinstance(audit, dict):
            audit["fallback_used"] = True

    @staticmethod
    def _fallback_used(resolved_inputs: dict[str, Any]) -> bool:
        audit = resolved_inputs.get("audit")
        return isinstance(audit, dict) and bool(audit.get("fallback_used", False))


class EntityResolutionError(ValueError):
    def __init__(self, summary: str) -> None:
        super().__init__(summary)
        self.summary = summary
