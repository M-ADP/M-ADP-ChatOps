from __future__ import annotations

from chatops.graph.specialists.base import BaseSpecialist


class ProjectSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="project")
