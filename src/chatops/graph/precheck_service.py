from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrecheckService:
    downstream_dispatcher: Any

    def run(
        self,
        *,
        operation: Any,
        resolved_inputs: dict[str, Any],
        user_id: str,
        user_role: str | None,
    ) -> dict[str, Any]:
        references = resolved_inputs.get("references", {})
        resolved_ids: dict[str, Any] = {}

        if not hasattr(self.downstream_dispatcher, "project_client"):
            return {"error": None, "resolved_ids": resolved_ids}

        project_name = references.get("project_name")
        if self._operation_needs_project(operation.id) and project_name:
            try:
                result = self._run_awaitable(
                    self._precheck_project(user_id=user_id, user_role=user_role, project_name=str(project_name))
                )
                if result.get("error"):
                    return result
                resolved_ids["project_id"] = result["project_id"]
                if result.get("similar_names"):
                    resolved_ids["similar_project_names"] = result["similar_names"]
            except Exception as exc:
                logger.error("Pre-check project failed: %s", exc, exc_info=True)
                return {"error": "리소스 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}

        application_name = references.get("application_name")
        if self._operation_needs_application(operation.id) and application_name and resolved_ids.get("project_id"):
            try:
                result = self._run_awaitable(
                    self._precheck_application(
                        user_id=user_id,
                        user_role=user_role,
                        project_id=int(resolved_ids["project_id"]),
                        app_name=str(application_name),
                    )
                )
                if result.get("error"):
                    return result
                resolved_ids["application_id"] = result.get("application_id")
            except Exception as exc:
                logger.error("Pre-check application failed: %s", exc, exc_info=True)
                return {"error": "리소스 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}

        target_nickname = references.get("target_nickname")
        if self._operation_needs_target_user(operation.id) and target_nickname:
            try:
                result = self._run_awaitable(self._precheck_user(str(target_nickname)))
                if result.get("error"):
                    return result
                resolved_ids["target_user_id"] = result["user_id"]
            except Exception as exc:
                logger.error("Pre-check user failed: %s", exc, exc_info=True)
                return {"error": "리소스 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}

        return {"error": None, "resolved_ids": resolved_ids}

    async def _precheck_project(
        self,
        *,
        user_id: str,
        user_role: str | None,
        project_name: str,
    ) -> dict[str, Any]:
        projects = await self.downstream_dispatcher.project_client.list_projects(user_id=user_id, role=user_role)
        if projects.get("success") is False:
            return {"error": str(projects.get("summary", "프로젝트 목록을 조회하지 못했습니다."))}
        items = projects.get("items", [])
        all_names = [str(item.get("name", "")) for item in items if isinstance(item, dict)]

        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("name")) == project_name:
                return {"error": None, "project_id": int(item["id"])}

        similar = self._find_similar_names(project_name, all_names, limit=3)
        message = f"프로젝트 '{project_name}'을(를) 찾을 수 없습니다."
        if similar:
            message += "\n비슷한 이름의 프로젝트:\n" + "\n".join(f"- {name}" for name in similar)
        message += "\n다시 확인해주세요."
        return {"error": message, "similar_names": similar}

    async def _precheck_application(
        self,
        *,
        user_id: str,
        user_role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]:
        status_result = await self.downstream_dispatcher.application_client.get_apps_status(
            user_id=user_id,
            role=user_role,
            project_id=project_id,
            app_name=app_name,
        )
        if status_result.get("success") is False:
            return {"error": f"앱 '{app_name}'을(를) 찾을 수 없습니다. 다시 확인해주세요."}
        app_id = status_result.get("app_id")
        if app_id is None and isinstance(status_result.get("data"), dict):
            data = status_result["data"]
            app_id = data.get("appId") or data.get("app_id")
        return {"error": None, "application_id": app_id}

    async def _precheck_user(self, nickname: str) -> dict[str, Any]:
        if getattr(self.downstream_dispatcher, "user_client", None) is None:
            return {"error": "사용자 조회 서비스를 사용할 수 없습니다."}
        profile = await self.downstream_dispatcher.user_client.get_profile_by_nickname(nickname=nickname)
        if profile.get("success") is False:
            return {"error": f"사용자 '{nickname}'을(를) 찾을 수 없습니다. 닉네임을 다시 확인해주세요."}
        data = profile.get("data")
        if not isinstance(data, dict) or data.get("id") is None:
            return {"error": f"사용자 '{nickname}'을(를) 찾을 수 없습니다."}
        return {"error": None, "user_id": int(data["id"])}

    @staticmethod
    def _operation_needs_project(operation_id: str) -> bool:
        return operation_id not in {"project.create", "project.list_projects"}

    @staticmethod
    def _operation_needs_application(operation_id: str) -> bool:
        return operation_id in {
            "application.delete_apps",
            "application.patch_apps_resources",
            "application.patch_apps_github",
        }

    @staticmethod
    def _operation_needs_target_user(operation_id: str) -> bool:
        return operation_id in {
            "project.add_member",
            "project.remove_member",
            "project.transfer_ownership",
        }

    @staticmethod
    def _find_similar_names(target: str, names: list[str], limit: int = 3) -> list[str]:
        target_lower = target.lower()
        scored = []
        for name in names:
            name_lower = name.lower()
            if target_lower in name_lower or name_lower in target_lower:
                scored.append((name, 2))
            elif any(c in name_lower for c in target_lower if c.isalnum()):
                common = sum(1 for c in target_lower if c in name_lower)
                scored.append((name, common))
        scored.sort(key=lambda item: -item[1])
        return [name for name, _ in scored[:limit]]

    @staticmethod
    def _run_awaitable(awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("async downstream 호출은 현재 sync workflow에서만 지원합니다.")
