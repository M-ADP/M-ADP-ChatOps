from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chatops.common.id_generator import IdGenerator


@dataclass
class FakeApplicationClientImpl:
    apps_by_user: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    async def create_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        del role
        app = {
            "application_id": IdGenerator.generate_sonyflake_id(),
            "name": str(body.get("name", "unnamed-app")),
            "project_id": int(body.get("project_id", 0)),
            "cpu": body.get("cpu"),
            "memory": body.get("memory"),
            "disk": body.get("disk"),
            "port": body.get("port"),
            "github": None,
            "status": "RUNNING",
            "current_instances": 1,
            "available_instances": 1,
        }
        self.apps_by_user.setdefault(user_id, []).append(app)
        return {"summary": "application.create_apps", "data": app, "status_code": 201}

    async def get_apps(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]:
        del role
        items = [
            {
                "name": str(app.get("name")),
                "pod_count": int(app.get("current_instances", 1)),
                "port": int(app.get("port", 0) or 0),
                "cpu_usage_percentage": 10,
                "memory_usage_percentage": 20,
            }
            for app in self.apps_by_user.get(user_id, [])
            if int(app.get("project_id", 0)) == int(project_id)
        ]
        if not items:
            return {"summary": "애플리케이션 목록이 없습니다.", "items": []}
        return {"summary": ", ".join(item["name"] for item in items), "items": items}

    async def delete_apps(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        del role
        application_id = int(body["application_id"])
        apps = self.apps_by_user.get(user_id, [])
        for index, app in enumerate(apps):
            if int(app.get("application_id", 0)) == application_id:
                apps.pop(index)
                return {"summary": "application.delete_apps", "status_code": 200}
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def patch_apps_resources(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        del role
        application_id = int(body["application_id"])
        apps = self.apps_by_user.get(user_id, [])
        for app in apps:
            if int(app.get("application_id", 0)) == application_id:
                app["cpu"] = body.get("max_cpu")
                app["memory"] = body.get("max_memory")
                app["disk"] = body.get("max_disk")
                return {"summary": "application.patch_apps_resources", "data": app, "status_code": 200}
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def patch_apps_github(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        del role
        application_id = int(body["appDeploymentId"])
        apps = self.apps_by_user.get(user_id, [])
        for app in apps:
            if int(app.get("application_id", 0)) == application_id:
                app["github"] = {
                    "owner": body.get("owner"),
                    "repository": body.get("repository"),
                    "branch": body.get("branch"),
                }
                return {"summary": "application.patch_apps_github", "data": app, "status_code": 200}
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def get_apps_status(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]:
        del role
        apps = self.apps_by_user.get(user_id, [])
        for app in apps:
            if int(app.get("project_id", 0)) == int(project_id) and str(app.get("name")) == str(app_name):
                return {
                    "summary": (
                        f"{app_name} 앱 상태: CPU 10%, 인스턴스 "
                        f"{app.get('current_instances', 1)}/{app.get('available_instances', 1)}"
                    ),
                    "app_id": int(app["application_id"]),
                    "data": {
                        "appId": int(app["application_id"]),
                        "cpu_usage_percentage": 10,
                        "memory_used": "256Mi",
                        "memory_total": "512Mi",
                        "disk_used": "1Gi",
                        "disk_total": "10Gi",
                        "current_instances": int(app.get("current_instances", 1)),
                        "available_instances": int(app.get("available_instances", 1)),
                    },
                    "status_code": 200,
                }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def get_apps_logs(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]:
        del role
        apps = self.apps_by_user.get(user_id, [])
        for app in apps:
            if int(app.get("project_id", 0)) == int(project_id) and str(app.get("name")) == str(app_name):
                return {"summary": f"{app_name} 앱 로그", "data": "line1\nline2"}
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def get_apps_details(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, Any]:
        del role
        apps = self.apps_by_user.get(user_id, [])
        for app in apps:
            if int(app.get("project_id", 0)) == int(project_id) and str(app.get("name")) == str(app_name):
                github = app.get("github") or {}
                repo_url = (
                    f"https://github.com/{github.get('owner')}/{github.get('repository')}"
                    if github.get("owner") and github.get("repository")
                    else ""
                )
                return {
                    "summary": f"{app_name} 앱 상세: 포트 {app.get('port')}, 상태 {app.get('status', 'RUNNING')}",
                    "data": {
                        "app_id": int(app["application_id"]),
                        "port": int(app.get("port", 0) or 0),
                        "resource_use_percentage": 30,
                        "github_repository_url": repo_url,
                        "status": str(app.get("status", "RUNNING")),
                    },
                }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}
