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

    def list_after_sequence(self, request_id: int, sequence: int) -> list[RequestEventRecord]:
        return self.repository.list_after_sequence(request_id=request_id, sequence=sequence)
