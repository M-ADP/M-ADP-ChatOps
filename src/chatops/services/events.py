from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from chatops.db.models import RequestEventRecord
from chatops.db.repositories import RequestEventRepository


class EventService:
    def __init__(self, session: Session) -> None:
        self.repository = RequestEventRepository(session)

    def append_event(
        self,
        request_id: int,
        session_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> RequestEventRecord:
        sequence = self.repository.get_latest_sequence(request_id) + 1
        return self.repository.append(
            request_id=request_id,
            session_id=session_id,
            sequence=sequence,
            event_type=event_type,
            payload=json.dumps(payload, ensure_ascii=False),
        )

    def append_audit_event(
        self,
        request_id: int,
        session_id: int,
        event_type: str,
        payload: dict[str, Any],
        audit_context: dict[str, Any] | None = None,
    ) -> RequestEventRecord:
        return self.append_event(
            request_id=request_id,
            session_id=session_id,
            event_type=event_type,
            payload=self.build_audit_payload(
                request_id=request_id,
                session_id=session_id,
                payload=payload,
                audit_context=audit_context,
            ),
        )

    @staticmethod
    def build_audit_payload(
        *,
        request_id: int,
        session_id: int,
        payload: dict[str, Any],
        audit_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized.setdefault("request_id", request_id)
        normalized.setdefault("session_id", session_id)
        context = audit_context or {}
        for key in ("user_id", "operation", "latency_ms", "downstream", "status_code"):
            normalized.setdefault(key, context.get(key))
        normalized.setdefault("fallback_used", bool(context.get("fallback_used", False)))
        normalized.setdefault("clarification_type", context.get("clarification_type"))
        return normalized

    def list_after_sequence(self, request_id: int, sequence: int) -> list[RequestEventRecord]:
        return self.repository.list_after_sequence(request_id=request_id, sequence=sequence)
