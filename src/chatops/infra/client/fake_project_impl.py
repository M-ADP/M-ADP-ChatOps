from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chatops.common.id_generator import IdGenerator


@dataclass
class FakeProjectClientImpl:
    projects_by_user: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    async def create_project(self, *, user_id: str, role: str | None, body: dict[str, Any]) -> dict[str, Any]:
        del role
        project = {
            "id": IdGenerator.generate_sonyflake_id(),
            "name": str(body.get("name", "unnamed-project")),
            "my_role": "OWNER",
            "max_cpu": body.get("max_cpu"),
            "max_memory": body.get("max_memory"),
            "max_disk": body.get("max_disk"),
            "members": [
                {
                    "user_id": user_id,
                    "username": "current-user",
                    "nickname": "current-user",
                    "role": "OWNER",
                }
            ],
        }
        self.projects_by_user.setdefault(user_id, []).append(project)
        return {
            "success": True,
            "summary": "project.create",
            "data": project,
            "status_code": 201,
        }

    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, Any]:
        del role
        items = [
            {
                "id": project["id"],
                "name": project["name"],
                "my_role": project.get("my_role", "OWNER"),
            }
            for project in self.projects_by_user.get(user_id, [])
        ]
        if not items:
            return {"summary": "프로젝트 목록이 없습니다.", "items": []}
        return {
            "summary": ", ".join(str(item.get("name")) for item in items),
            "items": items,
        }

    async def get_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) == int(project_id):
                return {
                    "summary": f"{project['name']} 프로젝트 상세",
                    "data": {
                        "id": project["id"],
                        "name": project["name"],
                        "my_role": project.get("my_role", "OWNER"),
                        "deployments": [],
                    },
                }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def get_project_resource_limit(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) == int(project_id):
                return {
                    "summary": (
                        f"{project['name']} 프로젝트 한도: CPU {project.get('max_cpu')}, "
                        f"메모리 {project.get('max_memory')}GB, 디스크 {project.get('max_disk')}GB"
                    ),
                    "data": {
                        "project_id": project["id"],
                        "max_cpu": project.get("max_cpu"),
                        "max_memory": project.get("max_memory"),
                        "max_disk": project.get("max_disk"),
                    },
                }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def check_project_available(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        status = any(int(project.get("id", 0)) == int(project_id) for project in projects)
        return {
            "summary": "프로젝트에 접근 가능합니다." if status else "프로젝트에 접근할 수 없습니다.",
            "data": {"status": status},
        }

    async def check_project_owner(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) == int(project_id):
                is_owner = str(project.get("my_role", "")).upper() == "OWNER"
                return {
                    "summary": "프로젝트 소유자입니다." if is_owner else "프로젝트 소유자가 아닙니다.",
                    "data": {"status": is_owner},
                }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def list_project_members(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) == int(project_id):
                items = list(project.get("members", []))
                summary = ", ".join(f"{item['username']}({item['role']})" for item in items) if items else "멤버가 없습니다."
                return {"summary": summary, "items": items}
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def add_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        del role
        target_user_id = int(body.get("user_id", 0))
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) != int(project_id):
                continue
            members = project.setdefault("members", [])
            if not any(int(item.get("user_id", 0)) == target_user_id for item in members):
                members.append(
                    {
                        "user_id": target_user_id,
                        "username": "member",
                        "nickname": "member",
                        "role": "MEMBER",
                    }
                )
            return {
                "success": True,
                "summary": "project.add_member",
                "data": {"project_id": project_id, "user_id": target_user_id},
                "status_code": 200,
            }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def remove_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        target_user_id: int,
    ) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) != int(project_id):
                continue
            members = project.setdefault("members", [])
            project["members"] = [item for item in members if int(item.get("user_id", 0)) != int(target_user_id)]
            return {
                "success": True,
                "summary": "project.remove_member",
                "data": {"project_id": project_id, "target_user_id": target_user_id},
                "status_code": 200,
            }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def transfer_project_ownership(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        del role
        target_user_id = int(body.get("target_user_id", 0))
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) != int(project_id):
                continue
            members = project.setdefault("members", [])
            found = False
            for member in members:
                member["role"] = "OWNER" if int(member.get("user_id", 0)) == target_user_id else "MEMBER"
                if int(member.get("user_id", 0)) == target_user_id:
                    found = True
            if not found:
                members.append(
                    {
                        "user_id": target_user_id,
                        "username": "member",
                        "nickname": "member",
                        "role": "OWNER",
                    }
                )
            return {
                "success": True,
                "summary": "project.transfer_ownership",
                "data": {"project_id": project_id, "target_user_id": target_user_id},
                "status_code": 200,
            }
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def update_project_name(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) == int(project_id):
                project["name"] = str(body.get("name", project.get("name", "")))
                return {
                    "success": True,
                    "summary": "project.update_name",
                    "data": project,
                    "status_code": 200,
                }
        return {
            "success": False,
            "summary": "대상 리소스를 찾지 못했습니다.",
            "status_code": 404,
        }

    async def delete_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for index, project in enumerate(projects):
            if int(project.get("id", 0)) == int(project_id):
                projects.pop(index)
                return {
                    "success": True,
                    "summary": "project.delete",
                    "status_code": 200,
                }
        return {
            "success": False,
            "summary": "대상 리소스를 찾지 못했습니다.",
            "status_code": 404,
        }

    async def update_project_resource(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        del role
        projects = self.projects_by_user.get(user_id, [])
        for project in projects:
            if int(project.get("id", 0)) == int(project_id):
                project["max_cpu"] = body.get("max_cpu")
                project["max_memory"] = body.get("max_memory")
                project["max_disk"] = body.get("max_disk")
                return {
                    "success": True,
                    "summary": "project.update_resource",
                    "data": project,
                    "status_code": 200,
                }
        return {
            "success": False,
            "summary": "대상 리소스를 찾지 못했습니다.",
            "status_code": 404,
        }
