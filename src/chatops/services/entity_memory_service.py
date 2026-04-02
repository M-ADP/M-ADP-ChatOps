from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EntityMemoryService:
    def merge_into_session_context(
        self,
        *,
        session_context: dict[str, Any] | None,
        session_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(session_context or {})
        if isinstance(session_summary, dict):
            merged["session_summary"] = session_summary
            recent_entities = session_summary.get("recent_entities")
            if isinstance(recent_entities, dict) and recent_entities:
                merged["entity_memory"] = dict(recent_entities)
        return merged
