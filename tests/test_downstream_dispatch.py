from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chatops.services.registry import RegistryEntry
from chatops.services.downstream_dispatcher import DownstreamDispatcher


@dataclass
class RecordingProjectClient:
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def create_project(self, *, user_id: str, role: str | None, body: dict[str, object]) -> dict[str, object]:
        self.calls.append(("create_project", {"user_id": user_id, "role": role, "body": body}))
        return {"summary": "project.create"}

    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, object]:
        self.calls.append(("list_projects", {"user_id": user_id, "role": role}))
        return {
            "summary": "project.list_projects",
            "items": [
                {"id": 98, "name": "demo"},
                {"id": 99, "name": "other"},
            ],
        }

    async def update_project_name(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            (
                "update_project_name",
                {"user_id": user_id, "role": role, "project_id": project_id, "body": body},
            )
        )
        return {"summary": "project.update_name"}

    async def delete_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, object]:
        self.calls.append(("delete_project", {"user_id": user_id, "role": role, "project_id": project_id}))
        return {"summary": "project.delete"}

    async def update_project_resource(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            (
                "update_project_resource",
                {"user_id": user_id, "role": role, "project_id": project_id, "body": body},
            )
        )
        return {"summary": "project.update_resource"}

    async def get_project(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, object]:
        self.calls.append(("get_project", {"user_id": user_id, "role": role, "project_id": project_id}))
        return {"summary": "demo 프로젝트 상세", "data": {"id": project_id, "name": "demo"}}

    async def get_project_resource_limit(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, object]:
        self.calls.append(
            ("get_project_resource_limit", {"user_id": user_id, "role": role, "project_id": project_id})
        )
        return {
            "summary": "demo 프로젝트 한도: CPU 2, 메모리 1GB, 디스크 20GB",
            "data": {"project_id": project_id, "max_cpu": 2, "max_memory": 1, "max_disk": 20},
        }

    async def check_project_available(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, object]:
        self.calls.append(
            ("check_project_available", {"user_id": user_id, "role": role, "project_id": project_id})
        )
        return {"summary": "demo 프로젝트에 접근 가능합니다.", "data": {"status": True}}

    async def check_project_owner(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, object]:
        self.calls.append(("check_project_owner", {"user_id": user_id, "role": role, "project_id": project_id}))
        return {"summary": "demo 프로젝트 소유자입니다.", "data": {"status": True}}

    async def list_project_members(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
    ) -> dict[str, object]:
        self.calls.append(("list_project_members", {"user_id": user_id, "role": role, "project_id": project_id}))
        return {
            "summary": "demo 프로젝트 멤버: alice(OWNER), bob(MEMBER)",
            "items": [
                {"username": "alice", "role": "OWNER"},
                {"username": "bob", "role": "MEMBER"},
            ],
        }

    async def add_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            (
                "add_project_member",
                {"user_id": user_id, "role": role, "project_id": project_id, "body": body},
            )
        )
        return {"summary": "project.add_member"}

    async def remove_project_member(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        target_user_id: int,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "remove_project_member",
                {
                    "user_id": user_id,
                    "role": role,
                    "project_id": project_id,
                    "target_user_id": target_user_id,
                },
            )
        )
        return {"summary": "project.remove_member"}

    async def transfer_project_ownership(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        body: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            (
                "transfer_project_ownership",
                {"user_id": user_id, "role": role, "project_id": project_id, "body": body},
            )
        )
        return {"summary": "project.transfer_ownership"}


@dataclass
class FailingProjectClient(RecordingProjectClient):
    async def create_project(self, *, user_id: str, role: str | None, body: dict[str, object]) -> dict[str, object]:
        self.calls.append(("create_project", {"user_id": user_id, "role": role, "body": body}))
        return {"success": False, "summary": "요청값이 올바르지 않습니다.", "status_code": 422}


@dataclass
class RecordingApplicationClient:
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def create_apps(self, *, user_id: str, role: str | None, body: dict[str, object]) -> dict[str, object]:
        self.calls.append(("create_apps", {"user_id": user_id, "role": role, "body": body}))
        return {"summary": "application.create_apps"}

    async def delete_apps(self, *, user_id: str, role: str | None, body: dict[str, object]) -> dict[str, object]:
        self.calls.append(("delete_apps", {"user_id": user_id, "role": role, "body": body}))
        return {"summary": "application.delete_apps"}

    async def patch_apps_resources(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(("patch_apps_resources", {"user_id": user_id, "role": role, "body": body}))
        return {"summary": "application.patch_apps_resources"}

    async def patch_apps_github(
        self,
        *,
        user_id: str,
        role: str | None,
        body: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(("patch_apps_github", {"user_id": user_id, "role": role, "body": body}))
        return {"summary": "application.patch_apps_github"}

    async def get_apps_status(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_apps_status",
                {"user_id": user_id, "role": role, "project_id": project_id, "app_name": app_name},
            )
        )
        return {"summary": "application.get_apps_status", "data": {"appId": 777}}

    async def get_apps(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, object]:
        self.calls.append(("get_apps", {"user_id": user_id, "role": role, "project_id": project_id}))
        return {
            "summary": "demo 프로젝트 앱 목록: api-demo, web-demo",
            "items": [
                {"name": "api-demo", "port": 8080},
                {"name": "web-demo", "port": 3000},
            ],
        }

    async def get_apps_logs(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, object]:
        self.calls.append(
            ("get_apps_logs", {"user_id": user_id, "role": role, "project_id": project_id, "app_name": app_name})
        )
        return {"summary": "demo 프로젝트 api-demo 앱 로그", "data": "line1\nline2"}

    async def get_apps_details(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_name: str,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_apps_details",
                {"user_id": user_id, "role": role, "project_id": project_id, "app_name": app_name},
            )
        )
        return {
            "summary": "demo 프로젝트 api-demo 앱 상세: 포트 8080, 상태 RUNNING",
            "data": {"app_id": 777, "port": 8080, "status": "RUNNING"},
        }


@dataclass
class RecordingMonitoringClient:
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def get_app_deployment_traffic(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_deployment_name: str,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_app_deployment_traffic",
                {
                    "user_id": user_id,
                    "role": role,
                    "project_id": project_id,
                    "app_deployment_name": app_deployment_name,
                },
            )
        )
        return {"summary": "monitoring.get_app_deployment_traffic"}


@dataclass
class RecordingUserClient:
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def get_profile_by_nickname(self, *, nickname: str) -> dict[str, object]:
        self.calls.append(("get_profile_by_nickname", {"nickname": nickname}))
        return {"summary": "user.get_profile_by_nickname", "data": {"id": 321, "nickname": nickname}}


def _entry(
    *,
    entry_id: str,
    method: str,
    path: str,
    source_file: str,
    operation_kind: str,
) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file=source_file,
        operation_id=entry_id,
        path=path,
        method=method,
        summary=entry_id,
        capability=entry_id,
        usable_in=("query", "command"),
        operation_kind=operation_kind,
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=operation_kind != "read",
        risk_level="low",
        side_effects=(),
        required_headers=(),
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="",
        plan_template=(),
        examples=(),
    )


@pytest.mark.anyio
async def test_project_create_dispatches_to_project_client() -> None:
    project_client = RecordingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="project.create",
            method="POST",
            path="/projects",
            source_file="apis/project.yaml",
            operation_kind="write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"body": {"name": "demo"}},
    )

    assert result == {"success": True, "summary": "project.create", "result": {"summary": "project.create"}}
    assert project_client.calls == [
        ("create_project", {"user_id": "1", "role": "admin", "body": {"name": "demo"}})
    ]


@pytest.mark.anyio
async def test_project_list_dispatches_to_project_client() -> None:
    project_client = RecordingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_query(
        _entry(
            entry_id="project.list_projects",
            method="GET",
            path="/projects",
            source_file="apis/project.yaml",
            operation_kind="read",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={},
    )

    assert result == {
        "summary": "project.list_projects",
        "items": [
            {"id": 98, "name": "demo"},
            {"id": 99, "name": "other"},
        ],
    }
    assert project_client.calls == [("list_projects", {"user_id": "1", "role": "admin"})]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("entry_id", "path", "expected_call"),
    [
        ("project.get", "/projects/{project_id}", "get_project"),
        ("project.get_resource_limit", "/projects/resource-limit", "get_project_resource_limit"),
        ("project.check_available", "/projects/available", "check_project_available"),
        ("project.check_owner", "/projects/owner", "check_project_owner"),
        ("project.list_members", "/projects/{project_id}/members", "list_project_members"),
    ],
)
async def test_project_query_operations_dispatch_with_resolved_project_id(
    entry_id: str,
    path: str,
    expected_call: str,
) -> None:
    project_client = RecordingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_query(
        _entry(
            entry_id=entry_id,
            method="GET",
            path=path,
            source_file="apis/project.yaml",
            operation_kind="read",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo"}},
    )

    assert "summary" in result
    assert project_client.calls[0] == ("list_projects", {"user_id": "1", "role": "admin"})
    assert project_client.calls[1] == (
        expected_call,
        {"user_id": "1", "role": "admin", "project_id": 98},
    )


@pytest.mark.anyio
async def test_project_update_name_dispatches_to_project_client() -> None:
    project_client = RecordingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="project.update_name",
            method="PATCH",
            path="/projects/{project_id}/name",
            source_file="apis/project.yaml",
            operation_kind="write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo"}, "body": {"name": "demo-renamed"}},
    )

    assert result == {
        "success": True,
        "summary": "project.update_name",
        "result": {"summary": "project.update_name"},
    }
    assert project_client.calls == [
        ("list_projects", {"user_id": "1", "role": "admin"}),
        (
            "update_project_name",
            {"user_id": "1", "role": "admin", "project_id": 98, "body": {"name": "demo-renamed"}},
        )
    ]


@pytest.mark.anyio
async def test_project_delete_dispatches_to_project_client() -> None:
    project_client = RecordingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="project.delete",
            method="DELETE",
            path="/projects/{project_id}",
            source_file="apis/project.yaml",
            operation_kind="delete",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo"}},
    )

    assert result == {
        "success": True,
        "summary": "project.delete",
        "result": {"summary": "project.delete"},
    }
    assert project_client.calls == [
        ("list_projects", {"user_id": "1", "role": "admin"}),
        ("delete_project", {"user_id": "1", "role": "admin", "project_id": 98})
    ]


@pytest.mark.anyio
async def test_application_create_dispatches_to_application_client() -> None:
    project_client = RecordingProjectClient()
    application_client = RecordingApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=application_client,
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="application.create_apps",
            method="POST",
            path="/apps",
            source_file="apis/application.yaml",
            operation_kind="write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo"}, "body": {"name": "demo"}},
    )

    assert result == {
        "success": True,
        "summary": "application.create_apps",
        "result": {"summary": "application.create_apps"},
    }
    assert application_client.calls == [
        ("create_apps", {"user_id": "1", "role": "admin", "body": {"name": "demo", "project_id": 98}})
    ]
    assert project_client.calls == [("list_projects", {"user_id": "1", "role": "admin"})]


@pytest.mark.anyio
async def test_application_delete_dispatches_with_resolved_application_id() -> None:
    project_client = RecordingProjectClient()
    application_client = RecordingApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=application_client,
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="application.delete_apps",
            method="DELETE",
            path="/apps",
            source_file="apis/application.yaml",
            operation_kind="delete",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo", "application_name": "api-demo"}},
    )

    assert result == {
        "success": True,
        "summary": "application.delete_apps",
        "result": {"summary": "application.delete_apps"},
    }
    assert application_client.calls == [
        ("get_apps_status", {"user_id": "1", "role": "admin", "project_id": 98, "app_name": "api-demo"}),
        ("delete_apps", {"user_id": "1", "role": "admin", "body": {"application_id": 777}}),
    ]
    assert project_client.calls == [("list_projects", {"user_id": "1", "role": "admin"})]


@pytest.mark.anyio
async def test_application_resource_update_dispatches_with_resolved_application_id() -> None:
    project_client = RecordingProjectClient()
    application_client = RecordingApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=application_client,
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="application.patch_apps_resources",
            method="PATCH",
            path="/apps/resources",
            source_file="apis/application.yaml",
            operation_kind="write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={
            "references": {"project_name": "demo", "application_name": "api-demo"},
            "body": {"max_cpu": 2, "max_memory": 1024, "max_disk": 12},
        },
    )

    assert result == {
        "success": True,
        "summary": "application.patch_apps_resources",
        "result": {"summary": "application.patch_apps_resources"},
    }
    assert application_client.calls == [
        ("get_apps_status", {"user_id": "1", "role": "admin", "project_id": 98, "app_name": "api-demo"}),
        (
            "patch_apps_resources",
            {
                "user_id": "1",
                "role": "admin",
                "body": {"application_id": 777, "max_cpu": 2, "max_memory": 1024, "max_disk": 12},
            },
        ),
    ]


@pytest.mark.anyio
async def test_application_github_update_dispatches_with_resolved_application_id() -> None:
    project_client = RecordingProjectClient()
    application_client = RecordingApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=application_client,
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="application.patch_apps_github",
            method="PATCH",
            path="/apps/github",
            source_file="apis/application.yaml",
            operation_kind="write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={
            "references": {"project_name": "demo", "application_name": "api-demo"},
            "body": {"owner": "M-ADP", "repository": "chatops", "branch": "main"},
        },
    )

    assert result == {
        "success": True,
        "summary": "application.patch_apps_github",
        "result": {"summary": "application.patch_apps_github"},
    }
    assert application_client.calls == [
        ("get_apps_status", {"user_id": "1", "role": "admin", "project_id": 98, "app_name": "api-demo"}),
        (
            "patch_apps_github",
            {
                "user_id": "1",
                "role": "admin",
                "body": {
                    "appDeploymentId": 777,
                    "owner": "M-ADP",
                    "repository": "chatops",
                    "branch": "main",
                },
            },
        ),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("entry_id", "path", "resolved_inputs", "expected_calls"),
    [
        (
            "application.get_apps",
            "/apps",
            {"references": {"project_name": "demo"}},
            [
                ("get_apps", {"user_id": "1", "role": "admin", "project_id": 98}),
            ],
        ),
        (
            "application.get_apps_status",
            "/apps/status",
            {"references": {"project_name": "demo", "application_name": "api-demo"}},
            [
                ("get_apps_status", {"user_id": "1", "role": "admin", "project_id": 98, "app_name": "api-demo"}),
            ],
        ),
        (
            "application.get_apps_logs",
            "/apps/logs",
            {"references": {"project_name": "demo", "application_name": "api-demo"}},
            [
                ("get_apps_logs", {"user_id": "1", "role": "admin", "project_id": 98, "app_name": "api-demo"}),
            ],
        ),
        (
            "application.get_apps_details",
            "/apps/details",
            {"references": {"project_name": "demo", "application_name": "api-demo"}},
            [
                (
                    "get_apps_details",
                    {"user_id": "1", "role": "admin", "project_id": 98, "app_name": "api-demo"},
                ),
            ],
        ),
    ],
)
async def test_application_query_operations_dispatch(
    entry_id: str,
    path: str,
    resolved_inputs: dict[str, object],
    expected_calls: list[tuple[str, object]],
) -> None:
    project_client = RecordingProjectClient()
    application_client = RecordingApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=application_client,
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_query(
        _entry(
            entry_id=entry_id,
            method="GET",
            path=path,
            source_file="apis/application.yaml",
            operation_kind="read",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs=resolved_inputs,
    )

    assert "summary" in result
    assert project_client.calls == [("list_projects", {"user_id": "1", "role": "admin"})]
    assert application_client.calls == expected_calls


@pytest.mark.anyio
async def test_project_update_resource_dispatches_to_project_client() -> None:
    project_client = RecordingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="project.update_resource",
            method="PATCH",
            path="/projects/{project_id}/resource",
            source_file="apis/project.yaml",
            operation_kind="write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={
            "references": {"project_name": "demo"},
            "body": {"max_cpu": 2, "max_memory": 1, "max_disk": 20},
        },
    )

    assert result == {
        "success": True,
        "summary": "project.update_resource",
        "result": {"summary": "project.update_resource"},
    }
    assert project_client.calls == [
        ("list_projects", {"user_id": "1", "role": "admin"}),
        (
            "update_project_resource",
            {
                "user_id": "1",
                "role": "admin",
                "project_id": 98,
                "body": {"max_cpu": 2, "max_memory": 1, "max_disk": 20},
            },
        ),
    ]


@pytest.mark.anyio
async def test_project_create_failure_is_not_wrapped_as_success() -> None:
    project_client = FailingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="project.create",
            method="POST",
            path="/projects",
            source_file="apis/project.yaml",
            operation_kind="write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"body": {"name": "demo"}},
    )

    assert result == {
        "success": False,
        "summary": "요청값이 올바르지 않습니다.",
        "status_code": 422,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("entry_id", "method", "path", "expected_call"),
    [
        (
            "project.add_member",
            "POST",
            "/projects/{project_id}/members",
            ("add_project_member", {"user_id": "1", "role": "admin", "project_id": 98, "body": {"user_id": 321}}),
        ),
        (
            "project.remove_member",
            "DELETE",
            "/projects/{project_id}/members/{target_user_id}",
            ("remove_project_member", {"user_id": "1", "role": "admin", "project_id": 98, "target_user_id": 321}),
        ),
        (
            "project.transfer_ownership",
            "PATCH",
            "/projects/{project_id}/owner",
            (
                "transfer_project_ownership",
                {"user_id": "1", "role": "admin", "project_id": 98, "body": {"target_user_id": 321}},
            ),
        ),
    ],
)
async def test_project_member_operations_dispatch_with_resolved_nickname(
    entry_id: str,
    method: str,
    path: str,
    expected_call: tuple[str, object],
) -> None:
    project_client = RecordingProjectClient()
    user_client = RecordingUserClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
        user_client=user_client,
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id=entry_id,
            method=method,
            path=path,
            source_file="apis/project.yaml",
            operation_kind="delete" if entry_id == "project.remove_member" else "write",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo", "target_nickname": "alice"}},
    )

    assert result["success"] is True
    assert user_client.calls == [("get_profile_by_nickname", {"nickname": "alice"})]
    assert project_client.calls[0] == ("list_projects", {"user_id": "1", "role": "admin"})
    assert project_client.calls[1] == expected_call


@pytest.mark.anyio
async def test_monitoring_query_dispatches_to_monitoring_client() -> None:
    project_client = RecordingProjectClient()
    monitoring_client = RecordingMonitoringClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=monitoring_client,
    )

    result = await dispatcher.execute_query(
        _entry(
            entry_id="monitoring.get_app_deployment_traffic",
            method="GET",
            path="/monitoring/app-deployment/{project_id}/{app_deployment_name}",
            source_file="apis/monitoring.yaml",
            operation_kind="read",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo", "application_name": "api-server"}},
    )

    assert result == {"summary": "monitoring.get_app_deployment_traffic"}
    assert monitoring_client.calls == [
        (
            "get_app_deployment_traffic",
            {
                "user_id": "1",
                "role": "admin",
                "project_id": 98,
                "app_deployment_name": "api-server",
            },
        )
    ]
    assert project_client.calls == [("list_projects", {"user_id": "1", "role": "admin"})]


@pytest.mark.anyio
async def test_command_dispatch_reuses_prechecked_resolved_ids() -> None:
    project_client = RecordingProjectClient()
    user_client = RecordingUserClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
        user_client=user_client,
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="project.remove_member",
            method="DELETE",
            path="/projects/{project_id}/members/{target_user_id}",
            source_file="apis/project.yaml",
            operation_kind="delete",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={
            "references": {"project_name": "demo", "target_nickname": "alice"},
            "resolved_ids": {"project_id": 98, "target_user_id": 321},
        },
    )

    assert result["success"] is True
    assert project_client.calls == [
        (
            "remove_project_member",
            {"user_id": "1", "role": "admin", "project_id": 98, "target_user_id": 321},
        )
    ]
    assert user_client.calls == []


@pytest.mark.anyio
async def test_application_resolution_falls_back_to_list_apps_on_not_found() -> None:
    project_client = RecordingProjectClient()

    @dataclass
    class FallbackApplicationClient(RecordingApplicationClient):
        async def get_apps_status(
            self,
            *,
            user_id: str,
            role: str | None,
            project_id: int,
            app_name: str,
        ) -> dict[str, object]:
            self.calls.append(
                (
                    "get_apps_status",
                    {"user_id": user_id, "role": role, "project_id": project_id, "app_name": app_name},
                )
            )
            return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

        async def get_apps(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, object]:
            self.calls.append(("get_apps", {"user_id": user_id, "role": role, "project_id": project_id}))
            return {
                "summary": "demo 프로젝트 앱 목록: api-demo",
                "items": [{"id": 777, "name": "api-demo"}],
            }

    application_client = FallbackApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=application_client,
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="application.delete_apps",
            method="DELETE",
            path="/apps",
            source_file="apis/application.yaml",
            operation_kind="delete",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo", "application_name": "api-demo"}},
    )

    assert result["success"] is True
    assert application_client.calls == [
        ("get_apps_status", {"user_id": "1", "role": "admin", "project_id": 98, "app_name": "api-demo"}),
        ("get_apps", {"user_id": "1", "role": "admin", "project_id": 98}),
        ("delete_apps", {"user_id": "1", "role": "admin", "body": {"application_id": 777}}),
    ]


@pytest.mark.anyio
async def test_project_resolution_returns_similar_name_suggestions() -> None:
    @dataclass
    class SuggestingProjectClient(RecordingProjectClient):
        async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, object]:
            self.calls.append(("list_projects", {"user_id": user_id, "role": role}))
            return {
                "summary": "project.list_projects",
                "items": [
                    {"id": 98, "name": "demo-prod"},
                    {"id": 99, "name": "demo-test"},
                ],
            }

    dispatcher = DownstreamDispatcher(
        project_client=SuggestingProjectClient(),
        application_client=RecordingApplicationClient(),
        monitoring_client=RecordingMonitoringClient(),
    )

    result = await dispatcher.execute_command(
        _entry(
            entry_id="project.delete",
            method="DELETE",
            path="/projects/{project_id}",
            source_file="apis/project.yaml",
            operation_kind="delete",
        ),
        user_id="1",
        user_role="admin",
        resolved_inputs={"references": {"project_name": "demo"}},
    )

    assert result["success"] is False
    assert "demo-prod" in result["summary"]
    assert "demo-test" in result["summary"]
