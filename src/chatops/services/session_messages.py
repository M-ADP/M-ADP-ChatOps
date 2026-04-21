from __future__ import annotations

import json
from typing import Iterable

from chatops.db.models import MessageRecord, RequestRecord, SessionRecord
from chatops.schemas.messages import ConversationMessage, SessionMessagesPageResponse
from chatops.schemas.runtime import PlanObject, SpecialistResult, VerifierDecision
from chatops.schemas.sessions import SessionListItem, SessionListResponse
from chatops.schemas.tasks import TaskSnapshot


class SessionMessageService:
    def build_message(self, record: MessageRecord) -> ConversationMessage:
        return ConversationMessage(
            message_id=f"msg_{record.id}",
            request_id=record.request_id,
            role=record.role,
            type=record.message_type,
            text=record.text,
            task=self._load_task_snapshot(record.task_snapshot),
            plan=self._load_plan_object(record.plan_object),
            verifier=self._load_verifier_decision(record.verifier_decision),
            specialist=self._load_specialist_result(record.specialist_result),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def build_session_list(
        self,
        sessions: list[SessionRecord],
        messages_by_session: dict[int, list[ConversationMessage]],
        *,
        limit: int,
        cursor: str | None,
    ) -> SessionListResponse:
        items_with_activity: list[tuple[SessionListItem, object]] = []
        for session in sessions:
            messages = messages_by_session.get(session.id, [])
            latest = messages[-1] if messages else None
            latest_at = (
                (latest.updated_at or latest.created_at)
                if latest is not None
                else (session.updated_at or session.created_at)
            )
            latest_preview = latest.text if latest is not None else None
            items_with_activity.append(
                (
                    SessionListItem(
                        session_id=session.id,
                        project_id=session.project_id,
                        title=session.title,
                        status=session.status,
                        last_message_preview=latest_preview,
                        last_message_at=latest_at,
                        unread_count=0,
                    ),
                    latest_at,
                )
            )

        items = [
            item
            for item, _ in sorted(
                items_with_activity,
                key=lambda pair: (pair[1], pair[0].session_id),
                reverse=True,
            )
        ]
        start = self._decode_offset_cursor(cursor)
        end = min(start + limit, len(items))
        return SessionListResponse(
            sessions=items[start:end],
            next_cursor=str(end) if end < len(items) else None,
            has_more=end < len(items),
        )

    def paginate_messages(
        self,
        messages: list[ConversationMessage],
        *,
        limit: int,
        before: str | None,
    ) -> SessionMessagesPageResponse:
        end = self._decode_before_cursor(before, len(messages))
        start = max(0, end - limit)
        return SessionMessagesPageResponse(
            messages=messages[start:end],
            next_cursor=str(start) if start > 0 else None,
            has_more=start > 0,
        )

    def latest_messages(self, records: list[MessageRecord], *, limit: int) -> list[ConversationMessage]:
        if limit <= 0:
            return []
        return [self.build_message(record) for record in records[-limit:]]

    def group_by_session(self, records: Iterable[MessageRecord]) -> dict[int, list[ConversationMessage]]:
        grouped: dict[int, list[ConversationMessage]] = {}
        for record in records:
            grouped.setdefault(record.session_id, []).append(self.build_message(record))
        return grouped

    def synthesize_messages_from_requests(self, requests: list[RequestRecord]) -> list[ConversationMessage]:
        messages: list[ConversationMessage] = []
        for record in requests:
            messages.append(
                ConversationMessage(
                    message_id=f"req_{record.id}_user",
                    request_id=record.id,
                    role="user",
                    type="text",
                    text=record.message_text,
                    plan=None,
                    verifier=None,
                    specialist=None,
                    created_at=record.created_at,
                    updated_at=record.created_at,
                )
            )
            task = self._load_task_snapshot(record.task_snapshot)
            text = self.assistant_text(record.final_response, record.task_snapshot)
            if text is None and task is None:
                continue
            messages.append(
                ConversationMessage(
                    message_id=f"req_{record.id}_assistant",
                    request_id=record.id,
                    role="assistant",
                    type="task" if task is not None else "text",
                    text=text,
                    task=task,
                    plan=self._load_plan_object(record.plan_object),
                    verifier=self._load_verifier_decision(record.verifier_decision),
                    specialist=self._load_specialist_result(record.specialist_result),
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            )
        return messages

    @staticmethod
    def assistant_text(final_response: str | None, task_snapshot: str | None) -> str | None:
        if final_response:
            return final_response
        task = SessionMessageService._load_task_snapshot(task_snapshot)
        if task is None:
            return None
        return task.summary or task.title

    @staticmethod
    def _load_task_snapshot(raw_value: str | None) -> TaskSnapshot | None:
        payload = SessionMessageService._load_dict(raw_value)
        if payload is None:
            return None
        return TaskSnapshot.model_validate(payload)

    @staticmethod
    def _load_plan_object(raw_value: str | None) -> PlanObject | None:
        payload = SessionMessageService._load_dict(raw_value)
        if payload is None:
            return None
        return PlanObject.model_validate(payload)

    @staticmethod
    def _load_verifier_decision(raw_value: str | None) -> VerifierDecision | None:
        payload = SessionMessageService._load_dict(raw_value)
        if payload is None:
            return None
        return VerifierDecision.model_validate(payload)

    @staticmethod
    def _load_specialist_result(raw_value: str | None) -> SpecialistResult | None:
        payload = SessionMessageService._load_dict(raw_value)
        if payload is None:
            return None
        return SpecialistResult.model_validate(payload)

    @staticmethod
    def _load_dict(raw_value: str | None) -> dict | None:
        if not raw_value:
            return None
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @staticmethod
    def _decode_offset_cursor(cursor: str | None) -> int:
        if not cursor:
            return 0
        try:
            return max(0, int(cursor))
        except ValueError:
            return 0

    @staticmethod
    def _decode_before_cursor(cursor: str | None, total: int) -> int:
        if not cursor:
            return total
        try:
            return max(0, min(total, int(cursor)))
        except ValueError:
            return total
