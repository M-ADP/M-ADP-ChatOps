from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SessionSummaryService:
    def build(
        self,
        *,
        message_text: str,
        plan_object: dict[str, Any] | None,
        task_snapshot: dict[str, Any] | None,
        verifier_decision: dict[str, Any] | None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        timestamp = (now or datetime.now(timezone.utc)).isoformat()
        entities = {}
        if isinstance(plan_object, dict):
            entities = dict(plan_object.get("entities") or {})
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
            "recent_entities": entities,
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
