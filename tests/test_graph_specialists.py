from __future__ import annotations

from dataclasses import dataclass

from chatops.graph.specialist_router import SpecialistRouter
from chatops.services.registry import RegistryEntry


@dataclass
class FakeRegistryService:
    def get_entry(self, entry_id: str) -> RegistryEntry | None:
        return RegistryEntry(
            id=entry_id,
            source_file=f"ai_registry/{entry_id}.ai.yaml",
            operation_id=entry_id.split(".")[-1],
            path="/dummy",
            method="POST",
            summary="dummy",
            capability="dummy",
            usable_in=("command",),
            operation_kind="write",
            when_to_use=(),
            when_not_to_use=(),
            requires_confirmation=True,
            risk_level="medium",
            side_effects=(),
            required_headers=("X-User-Id",),
            required_inputs={},
            preconditions=(),
            missing_info_questions=(),
            response_interpretation="dummy",
            plan_template=(),
            examples=(),
        )


def test_specialist_router_selects_application_specialist_from_operation() -> None:
    router = SpecialistRouter(registry_service=FakeRegistryService())

    specialist = router.for_operation("application.create_apps")
    result = specialist.describe(
        operation_id="application.create_apps",
        resolved_inputs={"name": "api"},
        missing_inputs=["cpu", "memory", "disk"],
    )

    assert result["specialist"] == "application"
    assert result["operation_id"] == "application.create_apps"
    assert result["resolved_inputs"]["name"] == "api"
    assert result["missing_inputs"] == ["cpu", "memory", "disk"]
