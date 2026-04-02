from __future__ import annotations

import pytest
from pydantic import ValidationError

from chatops.services.slots import MonitoringTrafficSlots, ProjectCreateSlots


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
