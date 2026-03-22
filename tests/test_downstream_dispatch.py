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
        return {"summary": "project.list_projects"}


@dataclass
class RecordingApplicationClient:
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def create_apps(self, *, user_id: str, role: str | None, body: dict[str, object]) -> dict[str, object]:
        self.calls.append(("create_apps", {"user_id": user_id, "role": role, "body": body}))
        return {"summary": "application.create_apps"}


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

    assert result == {"summary": "project.list_projects"}
    assert project_client.calls == [("list_projects", {"user_id": "1", "role": "admin"})]


@pytest.mark.anyio
async def test_application_create_dispatches_to_application_client() -> None:
    application_client = RecordingApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=RecordingProjectClient(),
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
        resolved_inputs={"body": {"name": "demo", "project_id": 1}},
    )

    assert result == {
        "success": True,
        "summary": "application.create_apps",
        "result": {"summary": "application.create_apps"},
    }
    assert application_client.calls == [
        ("create_apps", {"user_id": "1", "role": "admin", "body": {"name": "demo", "project_id": 1}})
    ]


@pytest.mark.anyio
async def test_monitoring_query_dispatches_to_monitoring_client() -> None:
    monitoring_client = RecordingMonitoringClient()
    dispatcher = DownstreamDispatcher(
        project_client=RecordingProjectClient(),
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
        resolved_inputs={"path": {"project_id": 98, "app_deployment_name": "api-server"}},
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
