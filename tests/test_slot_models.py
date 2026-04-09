from __future__ import annotations

import pytest
from pydantic import ValidationError

from chatops.services.slots import (
    ApplicationReferenceSlots,
    ApplicationResourceSlots,
    MonitoringTrafficSlots,
    ProjectCreateSlots,
    ProjectReferenceSlots,
    ProjectResourceSlots,
)


def test_project_create_slots_validate_required_fields() -> None:
    slots = ProjectCreateSlots.model_validate(
        {
            "name": "demo",
            "max_cpu": 1,
            "max_memory": 0.5,
            "max_disk": 10,
        }
    )

    assert slots.name == "demo"
    assert slots.max_cpu == 1
    assert slots.max_memory == 0.5
    assert slots.max_disk == 10


def test_project_create_slots_reject_blank_name() -> None:
    with pytest.raises(ValidationError):
        ProjectCreateSlots.model_validate(
            {
                "name": "   ",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }
        )


def test_monitoring_traffic_slots_require_ordered_window() -> None:
    slots = MonitoringTrafficSlots.model_validate(
        {
            "project_name": "demo",
            "application_name": "api-server",
            "start": "2026-03-29T00:00:00+09:00",
            "end": "2026-03-29T01:00:00+09:00",
        }
    )

    assert slots.project_name == "demo"
    assert slots.application_name == "api-server"
    assert slots.start.isoformat() == "2026-03-29T00:00:00+09:00"
    assert slots.end.isoformat() == "2026-03-29T01:00:00+09:00"


def test_application_resource_slots_require_positive_values() -> None:
    slots = ApplicationResourceSlots.model_validate(
        {
            "project_name": "demo",
            "application_name": "api",
            "max_cpu": 1.5,
            "max_memory": 1024,
            "max_disk": 20,
        }
    )

    assert slots.project_name == "demo"
    assert slots.application_name == "api"
    assert slots.max_cpu == 1.5
    assert slots.max_memory == 1024
    assert slots.max_disk == 20


def test_application_resource_slots_reject_non_positive_values() -> None:
    with pytest.raises(ValidationError):
        ApplicationResourceSlots.model_validate(
            {
                "project_name": "demo",
                "application_name": "api",
                "max_cpu": 0,
                "max_memory": -1,
                "max_disk": 0,
            }
        )


def test_project_reference_slots_strip_blank_values() -> None:
    slots = ProjectReferenceSlots.model_validate({"project_name": " demo "})

    assert slots.project_name == "demo"


def test_application_reference_slots_capture_project_and_app_names() -> None:
    slots = ApplicationReferenceSlots.model_validate(
        {
            "project_name": "demo",
            "application_name": "api-demo",
        }
    )

    assert slots.project_name == "demo"
    assert slots.application_name == "api-demo"


def test_project_resource_slots_validate_positive_values() -> None:
    slots = ProjectResourceSlots.model_validate(
        {
            "project_name": "demo",
            "max_cpu": 2,
            "max_memory": 4,
            "max_disk": 20,
        }
    )

    assert slots.project_name == "demo"
    assert slots.max_cpu == 2
    assert slots.max_memory == 4
    assert slots.max_disk == 20


def test_project_resource_slots_reject_non_positive_values() -> None:
    with pytest.raises(ValidationError):
        ProjectResourceSlots.model_validate(
            {
                "project_name": "demo",
                "max_cpu": 0,
                "max_memory": -1,
                "max_disk": 0,
            }
        )
