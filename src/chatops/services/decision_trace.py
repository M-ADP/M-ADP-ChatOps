from __future__ import annotations

import json
import logging
from typing import Any


logger = logging.getLogger("chatops.decision_trace")
_TRUNCATE_LIMIT = 240


def log_decision_trace(
    *,
    stage: str,
    request_id: int | None = None,
    session_id: int | None = None,
    user_id: str | None = None,
    decision: str,
    reason: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "event": "chatops.decision_trace",
        "stage": stage,
        "decision": decision,
        "reason": reason,
        "request_id": request_id,
        "session_id": session_id,
        "user_id": user_id,
        "data": _sanitize(data or {}),
    }
    logger.info("decision_trace %s", json.dumps(payload, ensure_ascii=False, default=str))


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        normalized = " ".join(value.split())
        if len(normalized) <= _TRUNCATE_LIMIT:
            return normalized
        return f"{normalized[:_TRUNCATE_LIMIT]}..."
    return value
