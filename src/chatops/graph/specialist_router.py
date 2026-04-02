from __future__ import annotations

from dataclasses import dataclass, field

from chatops.graph.specialists.application import ApplicationSpecialist
from chatops.graph.specialists.base import BaseSpecialist
from chatops.graph.specialists.monitoring import MonitoringSpecialist
from chatops.graph.specialists.project import ProjectSpecialist


@dataclass
class SpecialistRouter:
    registry_service: object | None = None
    specialists: dict[str, BaseSpecialist] = field(
        default_factory=lambda: {
            "project": ProjectSpecialist(),
            "application": ApplicationSpecialist(),
            "monitoring": MonitoringSpecialist(),
        }
    )

    def for_operation(self, operation_id: str | None) -> BaseSpecialist:
        if not operation_id:
            return ProjectSpecialist()
        specialist_name = operation_id.split(".", 1)[0]
        return self.specialists.get(specialist_name, ProjectSpecialist())
