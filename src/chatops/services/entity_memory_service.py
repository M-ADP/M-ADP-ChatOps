from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EntityMemoryService:
    def normalize_recent_entities(self, recent_entities: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
        normalized = {
            "projects": [],
            "applications": [],
            "users": [],
        }
        if not isinstance(recent_entities, dict):
            return normalized

        has_structured_buckets = any(key in recent_entities for key in normalized)
        if has_structured_buckets:
            for key in normalized:
                values = recent_entities.get(key)
                if isinstance(values, list):
                    normalized[key] = [dict(item) for item in values if isinstance(item, dict)]
            return normalized

        project_name = self._coerce_name(recent_entities.get("project_name"))
        application_name = self._coerce_name(recent_entities.get("application_name"))
        target_nickname = self._coerce_name(recent_entities.get("target_nickname"))
        if project_name:
            normalized["projects"].append({"canonical_name": project_name, "aliases": [project_name]})
        if application_name:
            app_entry: dict[str, Any] = {
                "canonical_name": application_name,
                "aliases": [application_name],
            }
            if project_name:
                app_entry["project_name"] = project_name
            normalized["applications"].append(app_entry)
        if target_nickname:
            user_entry: dict[str, Any] = {
                "canonical_name": target_nickname,
                "nickname": target_nickname,
                "aliases": [target_nickname],
            }
            if project_name:
                user_entry["project_name"] = project_name
            normalized["users"].append(user_entry)
        return normalized

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
            normalized = self.normalize_recent_entities(recent_entities if isinstance(recent_entities, dict) else None)
            if any(normalized.values()):
                merged["entity_memory"] = normalized
        return merged

    @staticmethod
    def _coerce_name(value: Any) -> str | None:
        if value is None:
            return None
        name = str(value).strip()
        return name or None
