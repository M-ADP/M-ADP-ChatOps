from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from chatops.services.entity_memory_service import EntityMemoryService


@dataclass(frozen=True)
class SessionSummaryService:
    entity_memory_service: EntityMemoryService = EntityMemoryService()

    def build(
        self,
        *,
        message_text: str,
        plan_object: dict[str, Any] | None,
        task_snapshot: dict[str, Any] | None,
        verifier_decision: dict[str, Any] | None,
        resolved_references: dict[str, Any] | None = None,
        resolved_ids: dict[str, Any] | None = None,
        previous_summary: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        timestamp = (now or datetime.now(timezone.utc)).isoformat()
        entities = {}
        if isinstance(plan_object, dict):
            entities = dict(plan_object.get("entities") or {})
        merged_entities = self._merge_recent_entities(
            previous_summary=previous_summary,
            plan_entities=entities,
            resolved_references=resolved_references,
            resolved_ids=resolved_ids,
        )
        active_goal = None
        if isinstance(plan_object, dict):
            active_goal = plan_object.get("goal")
        last_completed_task = None
        if isinstance(task_snapshot, dict) and task_snapshot.get("status") == "completed":
            last_completed_task = task_snapshot.get("title")
        last_verifier_decision = None
        if isinstance(verifier_decision, dict):
            last_verifier_decision = verifier_decision.get("decision")
        return {
            "active_goal": active_goal or message_text,
            "recent_entities": merged_entities,
            "last_completed_task": last_completed_task,
            "last_verifier_decision": last_verifier_decision,
            "updated_at": timestamp,
        }

    def load(self, raw_value: str | None) -> dict[str, object] | None:
        if not raw_value:
            return None
        try:
            loaded = json.loads(raw_value)
        except json.JSONDecodeError:
            return None
        if not isinstance(loaded, dict):
            return None
        return loaded

    def _merge_recent_entities(
        self,
        *,
        previous_summary: dict[str, Any] | None,
        plan_entities: dict[str, Any],
        resolved_references: dict[str, Any] | None,
        resolved_ids: dict[str, Any] | None,
    ) -> dict[str, list[dict[str, Any]]]:
        previous_recent_entities = None
        if isinstance(previous_summary, dict):
            raw_recent_entities = previous_summary.get("recent_entities")
            if isinstance(raw_recent_entities, dict):
                previous_recent_entities = raw_recent_entities
        merged = self.entity_memory_service.normalize_recent_entities(previous_recent_entities)
        references = dict(resolved_references or {})
        project_name = self._coerce_name(references.get("project_name") or plan_entities.get("project_name"))
        application_name = self._coerce_name(
            references.get("application_name") or plan_entities.get("application_name")
        )
        target_nickname = self._coerce_name(
            references.get("target_nickname") or plan_entities.get("target_nickname")
        )
        resolved_ids = dict(resolved_ids or {})

        if project_name:
            self._upsert_entity(
                merged["projects"],
                {
                    "canonical_name": project_name,
                    "aliases": [project_name],
                    "resolved_id": self._coerce_optional_int(resolved_ids.get("project_id")),
                },
            )
        if application_name:
            self._upsert_entity(
                merged["applications"],
                {
                    "canonical_name": application_name,
                    "aliases": [application_name],
                    "project_name": project_name,
                    "project_id": self._coerce_optional_int(resolved_ids.get("project_id")),
                    "resolved_id": self._coerce_optional_int(resolved_ids.get("application_id")),
                },
            )
        if target_nickname:
            self._upsert_entity(
                merged["users"],
                {
                    "canonical_name": target_nickname,
                    "nickname": target_nickname,
                    "aliases": [target_nickname],
                    "project_name": project_name,
                    "project_id": self._coerce_optional_int(resolved_ids.get("project_id")),
                    "resolved_id": self._coerce_optional_int(resolved_ids.get("target_user_id")),
                },
            )
        return merged

    def _upsert_entity(self, bucket: list[dict[str, Any]], entry: dict[str, Any]) -> None:
        canonical_name = self._coerce_name(entry.get("canonical_name"))
        if canonical_name is None:
            return
        project_name = self._coerce_name(entry.get("project_name"))
        merged_entry = dict(entry)
        merged_entry["canonical_name"] = canonical_name
        merged_entry["aliases"] = self._normalize_aliases(entry.get("aliases"), canonical_name)

        existing_index = None
        for index, existing in enumerate(bucket):
            if not isinstance(existing, dict):
                continue
            if existing.get("canonical_name") != canonical_name:
                continue
            existing_project_name = self._coerce_name(existing.get("project_name"))
            if existing_project_name != project_name:
                continue
            existing_index = index
            break

        if existing_index is not None:
            existing = dict(bucket.pop(existing_index))
            existing_aliases = self._normalize_aliases(existing.get("aliases"), canonical_name)
            merged_entry["aliases"] = self._normalize_aliases([*existing_aliases, *merged_entry["aliases"]], canonical_name)
            for key, value in existing.items():
                if key == "aliases":
                    continue
                if key not in merged_entry or merged_entry.get(key) is None:
                    merged_entry[key] = value
            for key, value in list(merged_entry.items()):
                if value is None:
                    merged_entry.pop(key)

        bucket.insert(0, merged_entry)
        del bucket[10:]

    @staticmethod
    def _normalize_aliases(raw_aliases: Any, canonical_name: str) -> list[str]:
        aliases: list[str] = []
        values = raw_aliases if isinstance(raw_aliases, list) else [raw_aliases]
        for value in values:
            if value is None:
                continue
            alias = str(value).strip()
            if not alias or alias in aliases:
                continue
            aliases.append(alias)
        if canonical_name not in aliases:
            aliases.insert(0, canonical_name)
        return aliases

    @staticmethod
    def _coerce_name(value: Any) -> str | None:
        if value is None:
            return None
        name = str(value).strip()
        return name or None

    @staticmethod
    def _coerce_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
