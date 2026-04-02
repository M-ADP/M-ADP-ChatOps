from __future__ import annotations

from dataclasses import dataclass

from chatops.graph.precheck_service import PrecheckService
from chatops.services.registry import RegistryEntry


@dataclass
class _ProjectClient:
    async def list_projects(self, user_id: str, role: str | None = None) -> dict[str, object]:
        del user_id, role
        return {
            "success": True,
            "items": [
                {"id": 7, "name": "demo"},
                {"id": 9, "name": "demo-ops"},
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
    async def get_profile_by_nickname(self, nickname: str) -> dict[str, object]:
        del nickname
        return {"success": True, "data": {"id": 321}}


@dataclass
class _Dispatcher:
    project_client: object = _ProjectClient()
    application_client: object = _ApplicationClient()
    user_client: object = _UserClient()


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
