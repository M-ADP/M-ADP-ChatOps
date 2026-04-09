from __future__ import annotations

from dataclasses import dataclass, field

from chatops.graph.precheck_service import PrecheckService
from chatops.services.registry import RegistryEntry


@dataclass
class _ProjectClient:
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    async def list_projects(self, user_id: str, role: str | None = None) -> dict[str, object]:
        self.calls.append(("list_projects", {"user_id": user_id, "role": role}))
        del user_id, role
        return {
            "success": True,
            "items": [
                {"id": 7, "name": "demo"},
                {"id": 9, "name": "demo-ops"},
            ],
        }

    async def list_project_members(
        self,
        user_id: str,
        role: str | None = None,
        project_id: int | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            ("list_project_members", {"user_id": user_id, "role": role, "project_id": project_id or 0})
        )
        return {
            "success": True,
            "items": [
                {"user_id": 321, "nickname": "alice", "username": "alice.sre", "role": "MEMBER"},
                {"user_id": 999, "nickname": "bob", "username": "bob.ops", "role": "MEMBER"},
            ],
        }


@dataclass
class _ApplicationClient:
    async def get_apps_status(
        self,
        user_id: str,
        role: str | None = None,
        project_id: int | None = None,
        app_name: str | None = None,
    ) -> dict[str, object]:
        del user_id, role, project_id, app_name
        return {
            "success": True,
            "app_id": 99,
        }


@dataclass
class _UserClient:
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    async def get_profile_by_nickname(self, nickname: str) -> dict[str, object]:
        self.calls.append(("get_profile_by_nickname", {"nickname": nickname}))
        del nickname
        return {"success": True, "data": {"id": 321}}


@dataclass
class _ExplodingUserClient:
    async def get_profile_by_nickname(self, nickname: str) -> dict[str, object]:
        del nickname
        raise AssertionError("fallback user lookup should not run")


@dataclass
class _Dispatcher:
    project_client: object = _ProjectClient()
    application_client: object = _ApplicationClient()
    user_client: object = _UserClient()


@dataclass
class _ExplodingProjectClient:
    async def list_projects(self, user_id: str, role: str | None = None) -> dict[str, object]:
        del user_id, role
        raise AssertionError("project lookup should not run")


@dataclass
class _ExplodingApplicationClient:
    async def get_apps_status(
        self,
        user_id: str,
        role: str | None = None,
        project_id: int | None = None,
        app_name: str | None = None,
    ) -> dict[str, object]:
        del user_id, role, project_id, app_name
        raise AssertionError("application lookup should not run")


def _entry(entry_id: str) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path="/test",
        method="POST",
        summary=entry_id,
        capability=entry_id,
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=(),
        required_headers=(),
        required_inputs={},
        important_inputs={},
    )


def test_precheck_service_returns_resolved_ids_without_mutating_inputs() -> None:
    service = PrecheckService(
        downstream_dispatcher=_Dispatcher(),
    )
    operation = _entry("application.patch_apps_github")
    resolved_inputs = {
        "references": {
            "project_name": "demo",
            "application_name": "api-server",
        }
    }

    result = service.run(
        operation=operation,
        resolved_inputs=resolved_inputs,
        user_id="u1",
        user_role="MEMBER",
    )

    assert result == {"error": None, "resolved_ids": {"project_id": 7, "application_id": 99}}
    assert resolved_inputs == {
        "references": {
            "project_name": "demo",
            "application_name": "api-server",
        }
    }


def test_precheck_service_reuses_existing_resolved_ids_without_lookup() -> None:
    service = PrecheckService(
        downstream_dispatcher=_Dispatcher(
            project_client=_ExplodingProjectClient(),
            application_client=_ExplodingApplicationClient(),
        ),
    )
    operation = _entry("application.patch_apps_github")
    resolved_inputs = {
        "references": {
            "project_name": "demo",
            "application_name": "api-server",
        },
        "resolved_ids": {"project_id": 7, "application_id": 99},
    }

    result = service.run(
        operation=operation,
        resolved_inputs=resolved_inputs,
        user_id="u1",
        user_role="MEMBER",
    )

    assert result == {"error": None, "resolved_ids": {"project_id": 7, "application_id": 99}}


def test_precheck_service_resolves_target_user_from_project_members_before_user_lookup() -> None:
    project_client = _ProjectClient()
    user_client = _ExplodingUserClient()
    service = PrecheckService(
        downstream_dispatcher=_Dispatcher(
            project_client=project_client,
            application_client=_ApplicationClient(),
            user_client=user_client,
        ),
    )
    operation = _entry("project.remove_member")
    resolved_inputs = {
        "references": {
            "project_name": "demo",
            "target_nickname": "alice.sre",
        },
        "resolved_ids": {"project_id": 7},
    }

    result = service.run(
        operation=operation,
        resolved_inputs=resolved_inputs,
        user_id="u1",
        user_role="MEMBER",
    )

    assert result == {"error": None, "resolved_ids": {"project_id": 7, "target_user_id": 321}}
    assert project_client.calls == [
        ("list_project_members", {"user_id": "u1", "role": "MEMBER", "project_id": 7}),
    ]
