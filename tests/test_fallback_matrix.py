from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chatops.services.downstream_dispatcher import DownstreamDispatcher
from chatops.services.registry import RegistryEntry


@dataclass
class _ProjectClient:
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, object]:
        self.calls.append(("list_projects", {"user_id": user_id, "role": role}))
        return {
            "success": True,
            "items": [{"id": 98, "name": "demo"}],
        }


@dataclass
class _SuggestingProjectClient(_ProjectClient):
    async def list_projects(self, *, user_id: str, role: str | None) -> dict[str, object]:
        self.calls.append(("list_projects", {"user_id": user_id, "role": role}))
        return {
            "success": True,
            "items": [
                {"id": 98, "name": "demo-prod"},
                {"id": 99, "name": "demo-test"},
            ],
        }


@dataclass
class _ApplicationClient:
    calls: list[tuple[str, object]] = field(default_factory=list)

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
        return {"success": False, "summary": "대상 리소스를 찾지 못했습니다.", "status_code": 404}

    async def get_apps(self, *, user_id: str, role: str | None, project_id: int) -> dict[str, object]:
        self.calls.append(("get_apps", {"user_id": user_id, "role": role, "project_id": project_id}))
        return {
            "success": True,
            "items": [
                {"id": 777, "name": "api-demo"},
                {"id": 778, "name": "api-test"},
            ],
        }


def _entry(entry_id: str) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path="/apps/logs",
        method="GET",
        summary=entry_id,
        capability=entry_id,
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=(),
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={},
    )


@pytest.mark.anyio
async def test_application_query_not_found_uses_list_apps_fallback_before_failing() -> None:
    project_client = _ProjectClient()
    application_client = _ApplicationClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=application_client,
        monitoring_client=object(),
    )

    result = await dispatcher.execute_query(
        _entry("application.get_apps_logs"),
        user_id="u1",
        user_role="MEMBER",
        resolved_inputs={"references": {"project_name": "demo", "application_name": "api-server"}},
    )

    assert result["success"] is False
    assert "비슷한 앱" in result["summary"]
    assert "api-demo" in result["summary"]
    assert application_client.calls == [
        ("get_apps_logs", {"user_id": "u1", "role": "MEMBER", "project_id": 98, "app_name": "api-server"}),
        ("get_apps", {"user_id": "u1", "role": "MEMBER", "project_id": 98}),
    ]


@pytest.mark.anyio
async def test_project_query_not_found_returns_similar_project_suggestions() -> None:
    project_client = _SuggestingProjectClient()
    dispatcher = DownstreamDispatcher(
        project_client=project_client,
        application_client=_ApplicationClient(),
        monitoring_client=object(),
    )

    result = await dispatcher.execute_query(
        _entry("project.get"),
        user_id="u1",
        user_role="MEMBER",
        resolved_inputs={"references": {"project_name": "demo"}},
    )

    assert result["success"] is False
    assert "비슷한 프로젝트" in result["summary"]
    assert "demo-prod" in result["summary"]
    assert "demo-test" in result["summary"]
    assert project_client.calls == [("list_projects", {"user_id": "u1", "role": "MEMBER"})]
