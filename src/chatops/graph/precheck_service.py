from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from chatops.services.name_matcher import match_name
from chatops.services.user_matcher import match_user

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
        resolved_ids: dict[str, Any] = dict(resolved_inputs.get("resolved_ids") or {})

        if not hasattr(self.downstream_dispatcher, "project_client"):
            return {"error": None, "resolved_ids": resolved_ids}

        project_name = references.get("project_name")
        if self._operation_needs_project(operation.id) and project_name and "project_id" not in resolved_ids:
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
        if (
            self._operation_needs_application(operation.id)
            and application_name
            and resolved_ids.get("project_id")
            and "application_id" not in resolved_ids
        ):
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
        if self._operation_needs_target_user(operation.id) and target_nickname and "target_user_id" not in resolved_ids:
            try:
                result = self._run_awaitable(
                    self._precheck_user(
                        nickname=str(target_nickname),
                        user_id=user_id,
                        user_role=user_role,
                        project_id=self._coerce_optional_int(resolved_ids.get("project_id")),
                    )
                )
                if result.get("disambiguation_required"):
                    # 부분적으로 resolve된 ids(project_id 등)를 함께 전달해 safety_gate가 활용할 수 있게 한다.
                    return {**result, "resolved_ids": resolved_ids}
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
        names_by_value: dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("name") is not None and item.get("id") is not None:
                names_by_value[str(item["name"])] = int(item["id"])
        matched = match_name(project_name, list(names_by_value.keys()))
        if matched.matched_name is not None:
            return {"error": None, "project_id": int(names_by_value[matched.matched_name])}

        similar = matched.suggestions
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
            apps = await self.downstream_dispatcher.application_client.get_apps(
                user_id=user_id,
                role=user_role,
                project_id=project_id,
            )
            items = apps.get("items", []) if isinstance(apps, dict) else []
            names_by_value: dict[str, Any] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                application_id = item.get("id") or item.get("appId") or item.get("app_id")
                if name is not None and application_id is not None:
                    names_by_value[str(name)] = application_id
            matched = match_name(app_name, list(names_by_value.keys()))
            if matched.matched_name is not None:
                return {"error": None, "application_id": int(names_by_value[matched.matched_name])}
            message = f"앱 '{app_name}'을(를) 찾을 수 없습니다. 다시 확인해주세요."
            if matched.suggestions:
                message = (
                    f"앱 '{app_name}'을(를) 찾을 수 없습니다.\n"
                    "비슷한 이름의 앱:\n"
                    + "\n".join(f"- {name}" for name in matched.suggestions)
                    + "\n다시 확인해주세요."
                )
            return {"error": message}
        app_id = status_result.get("app_id")
        if app_id is None and isinstance(status_result.get("data"), dict):
            data = status_result["data"]
            app_id = data.get("appId") or data.get("app_id")
        return {"error": None, "application_id": app_id}

    async def _precheck_user(
        self,
        *,
        nickname: str,
        user_id: str,
        user_role: str | None,
        project_id: int | None,
    ) -> dict[str, Any]:
        suggestions: list[str] = []
        if project_id is not None and hasattr(self.downstream_dispatcher.project_client, "list_project_members"):
            members = await self.downstream_dispatcher.project_client.list_project_members(
                user_id=user_id,
                role=user_role,
                project_id=project_id,
            )
            if members.get("success") is not False:
                items = members.get("items", [])
                # 동명이인 감지: 쿼리와 정확히 일치하는 닉네임/유저명이 2명 이상이면 중의성 오류
                ambiguous = [
                    item for item in items
                    if isinstance(item, dict) and any(
                        str(item.get(field) or "").strip() == nickname
                        for field in ("nickname", "username", "canonical_name")
                    )
                ]
                if len(ambiguous) > 1:
                    candidates = []
                    lines = []
                    for item in ambiguous:
                        display = next(
                            (str(item.get(f) or "").strip() for f in ("nickname", "canonical_name", "username") if item.get(f)),
                            nickname,
                        )
                        uid = item.get("user_id") or item.get("id") or item.get("resolved_id")
                        candidates.append({"display": display, "user_id": uid})
                        lines.append(f"- {display}" + (f" (ID: {uid})" if uid else ""))
                    # LLM을 거치지 않고 상태 머신이 직접 처리해야 하는 중의성 오류.
                    # safety_gate가 이를 감지해 interrupt()로 선택지 UI를 프론트에 전달한다.
                    return {
                        "error": (
                            f"'{nickname}'에 해당하는 사용자가 여러 명입니다:\n"
                            + "\n".join(lines)
                            + "\n정확한 ID나 고유한 닉네임으로 다시 요청해주세요."
                        ),
                        "disambiguation_required": True,
                        "candidates": candidates,
                    }
                matched = match_user(nickname, items)
                if matched.user_id is not None:
                    return {"error": None, "user_id": matched.user_id}
                suggestions = matched.suggestions

        if getattr(self.downstream_dispatcher, "user_client", None) is None:
            return {"error": self._user_not_found_message(nickname, suggestions)}
        profile = await self.downstream_dispatcher.user_client.get_profile_by_nickname(nickname=nickname)
        if profile.get("success") is False:
            return {"error": self._user_not_found_message(nickname, suggestions)}
        data = profile.get("data")
        if not isinstance(data, dict) or data.get("id") is None:
            return {"error": self._user_not_found_message(nickname, suggestions)}
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
            "project.invite_member",
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
    def _user_not_found_message(nickname: str, suggestions: list[str]) -> str:
        message = f"사용자 '{nickname}'을(를) 찾을 수 없습니다."
        if suggestions:
            message += "\n비슷한 이름의 사용자:\n" + "\n".join(f"- {name}" for name in suggestions)
        message += "\n닉네임을 다시 확인해주세요."
        return message

    @staticmethod
    def _coerce_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _run_awaitable(awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("async downstream 호출은 현재 sync workflow에서만 지원합니다.")
