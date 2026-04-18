from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from chatops.db.models import MessageRecord, RequestEventRecord, RequestRecord, SessionRecord
from chatops.domain.enums import RequestStatus, SessionStatus


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, user_id: str, title: str | None) -> SessionRecord:
        record = SessionRecord(
            user_id=user_id,
            title=title,
            status=SessionStatus.ACTIVE.value,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_for_user(self, session_id: int, user_id: str) -> SessionRecord | None:
        query = select(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.user_id == user_id,
        )
        return self.session.execute(query).scalar_one_or_none()

    def update_summary(self, session_id: int, user_id: str, session_summary: str | None) -> SessionRecord | None:
        record = self.get_for_user(session_id=session_id, user_id=user_id)
        if record is None:
            return None
        record.session_summary = session_summary
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_for_user(self, user_id: str) -> list[SessionRecord]:
        query = (
            select(SessionRecord)
            .where(SessionRecord.user_id == user_id)
            .order_by(SessionRecord.created_at.desc(), SessionRecord.id.desc())
        )
        return list(self.session.execute(query).scalars())

    def has_active_requests(self, session_id: int, user_id: str) -> bool:
        """세션 내 진행 중인 요청(non-terminal) 존재 여부를 반환한다."""
        terminal = [s.value for s in RequestStatus.terminal_statuses()]
        query = (
            select(RequestRecord.id)
            .where(
                RequestRecord.session_id == session_id,
                RequestRecord.user_id == user_id,
                RequestRecord.status.notin_(terminal),
            )
            .limit(1)
        )
        return self.session.execute(query).scalar_one_or_none() is not None

    def delete_for_user(self, session_id: int, user_id: str) -> bool:
        """세션과 연관 데이터를 모두 삭제한다.

        FK CASCADE가 없으므로 의존 순서대로 직접 삭제한다:
        request_events → messages → requests → sessions

        Returns:
            True  — 삭제 성공
            False — 세션이 없거나 소유권 불일치
        """
        record = self.get_for_user(session_id=session_id, user_id=user_id)
        if record is None:
            return False

        request_ids_query = select(RequestRecord.id).where(
            RequestRecord.session_id == session_id,
        )
        request_ids = [row[0] for row in self.session.execute(request_ids_query).all()]

        if request_ids:
            self.session.execute(
                delete(RequestEventRecord).where(RequestEventRecord.request_id.in_(request_ids))
            )

        self.session.execute(
            delete(MessageRecord).where(MessageRecord.session_id == session_id)
        )
        self.session.execute(
            delete(RequestRecord).where(RequestRecord.session_id == session_id)
        )
        self.session.execute(
            delete(SessionRecord).where(
                SessionRecord.id == session_id,
                SessionRecord.user_id == user_id,
            )
        )
        self.session.commit()
        return True


class RequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        effective_message_text: str | None = None,
        request_id: int | None = None,
        request_type: str | None = None,
        requires_approval: bool = False,
    ) -> RequestRecord:
        payload = dict(
            session_id=session_id,
            user_id=user_id,
            message_text=message_text,
            effective_message_text=effective_message_text,
            request_type=request_type,
            status=RequestStatus.CREATED.value,
            requires_approval=requires_approval,
        )
        if request_id is not None:
            payload["id"] = request_id
        record = RequestRecord(**payload)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_for_user(self, request_id: int, user_id: str) -> RequestRecord | None:
        query = select(RequestRecord).where(
            RequestRecord.id == request_id,
            RequestRecord.user_id == user_id,
        )
        return self.session.execute(query).scalar_one_or_none()

    def get_latest_for_session(self, session_id: int, user_id: str) -> RequestRecord | None:
        query = (
            select(RequestRecord)
            .where(
                RequestRecord.session_id == session_id,
                RequestRecord.user_id == user_id,
            )
            .order_by(RequestRecord.created_at.desc(), RequestRecord.id.desc())
            .limit(1)
        )
        return self.session.execute(query).scalar_one_or_none()

    def list_recent_for_session(self, session_id: int, user_id: str, limit: int = 10) -> list[RequestRecord]:
        query = (
            select(RequestRecord)
            .where(
                RequestRecord.session_id == session_id,
                RequestRecord.user_id == user_id,
            )
            .order_by(RequestRecord.created_at.desc(), RequestRecord.id.desc())
            .limit(limit)
        )
        return list(self.session.execute(query).scalars())

    def list_for_session(self, session_id: int, user_id: str) -> list[RequestRecord]:
        query = (
            select(RequestRecord)
            .where(
                RequestRecord.session_id == session_id,
                RequestRecord.user_id == user_id,
            )
            .order_by(RequestRecord.created_at.asc(), RequestRecord.id.asc())
        )
        return list(self.session.execute(query).scalars())

    def list_page_for_session(
        self,
        session_id: int,
        user_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        request_type: str | None = None,
        ascending: bool = False,
        query_text: str | None = None,
    ) -> tuple[list[RequestRecord], int]:
        filters = [
            RequestRecord.session_id == session_id,
            RequestRecord.user_id == user_id,
        ]
        if status:
            filters.append(RequestRecord.status == status)
        if request_type:
            filters.append(RequestRecord.request_type == request_type)
        if query_text:
            term = f"%{query_text.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(RequestRecord.message_text).like(term),
                    func.lower(func.coalesce(RequestRecord.effective_message_text, "")).like(term),
                    func.lower(func.coalesce(RequestRecord.final_response, "")).like(term),
                )
            )

        order_by = (
            (RequestRecord.created_at.asc(), RequestRecord.id.asc())
            if ascending
            else (RequestRecord.created_at.desc(), RequestRecord.id.desc())
        )
        total_query = select(func.count()).select_from(RequestRecord).where(*filters)
        items_query = (
            select(RequestRecord)
            .where(*filters)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        total = int(self.session.execute(total_query).scalar_one())
        items = list(self.session.execute(items_query).scalars())
        return items, total

    def search_for_user(
        self,
        user_id: str,
        query_text: str,
        *,
        limit: int = 20,
        offset: int = 0,
        session_id: int | None = None,
    ) -> tuple[list[RequestRecord], int]:
        term = f"%{query_text.strip().lower()}%"
        filters = [RequestRecord.user_id == user_id]
        if session_id is not None:
            filters.append(RequestRecord.session_id == session_id)
        filters.append(
            or_(
                func.lower(RequestRecord.message_text).like(term),
                func.lower(func.coalesce(RequestRecord.effective_message_text, "")).like(term),
                func.lower(func.coalesce(RequestRecord.final_response, "")).like(term),
            )
        )

        total_query = select(func.count()).select_from(RequestRecord).where(*filters)
        items_query = (
            select(RequestRecord)
            .where(*filters)
            .order_by(RequestRecord.updated_at.desc(), RequestRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
        total = int(self.session.execute(total_query).scalar_one())
        items = list(self.session.execute(items_query).scalars())
        return items, total

    def update_status(self, request_id: int, status: str) -> RequestRecord | None:
        record = self.session.get(RequestRecord, request_id)
        if record is None:
            return None
        record.status = status
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_runtime_metadata(
        self,
        request_id: int,
        *,
        plan_object: str | None = None,
        verifier_decision: str | None = None,
        specialist_result: str | None = None,
    ) -> RequestRecord | None:
        record = self.session.get(RequestRecord, request_id)
        if record is None:
            return None
        record.plan_object = plan_object
        record.verifier_decision = verifier_decision
        record.specialist_result = specialist_result
        self.session.commit()
        self.session.refresh(record)
        return record


class RequestEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        request_id: int,
        session_id: int,
        sequence: int,
        event_type: str,
        payload: str,
    ) -> RequestEventRecord:
        record = RequestEventRecord(
            request_id=request_id,
            session_id=session_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_after_sequence(self, request_id: int, sequence: int) -> list[RequestEventRecord]:
        query = (
            select(RequestEventRecord)
            .where(
                RequestEventRecord.request_id == request_id,
                RequestEventRecord.sequence > sequence,
            )
            .order_by(RequestEventRecord.sequence.asc())
        )
        return list(self.session.execute(query).scalars())

    def list_for_request(
        self,
        request_id: int,
        session_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
    ) -> tuple[list[RequestEventRecord], int]:
        filters = [
            RequestEventRecord.request_id == request_id,
            RequestEventRecord.session_id == session_id,
        ]
        if event_type:
            filters.append(RequestEventRecord.event_type == event_type)

        total_query = select(func.count()).select_from(RequestEventRecord).where(*filters)
        items_query = (
            select(RequestEventRecord)
            .where(*filters)
            .order_by(RequestEventRecord.sequence.asc())
            .offset(offset)
            .limit(limit)
        )
        total = int(self.session.execute(total_query).scalar_one())
        items = list(self.session.execute(items_query).scalars())
        return items, total

    def get_latest_sequence(self, request_id: int) -> int:
        query = (
            select(RequestEventRecord.sequence)
            .where(RequestEventRecord.request_id == request_id)
            .order_by(RequestEventRecord.sequence.desc())
            .limit(1)
        )
        latest = self.session.execute(query).scalar_one_or_none()
        return int(latest or 0)


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        session_id: int,
        user_id: str,
        role: str,
        message_type: str,
        text: str | None = None,
        request_id: int | None = None,
        task_snapshot: str | None = None,
        plan_object: str | None = None,
        verifier_decision: str | None = None,
        specialist_result: str | None = None,
    ) -> MessageRecord:
        record = MessageRecord(
            session_id=session_id,
            request_id=request_id,
            user_id=user_id,
            role=role,
            message_type=message_type,
            text=text,
            task_snapshot=task_snapshot,
            plan_object=plan_object,
            verifier_decision=verifier_decision,
            specialist_result=specialist_result,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_assistant_for_request(self, request_id: int, user_id: str) -> MessageRecord | None:
        query = (
            select(MessageRecord)
            .where(
                MessageRecord.request_id == request_id,
                MessageRecord.user_id == user_id,
                MessageRecord.role == "assistant",
            )
            .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
            .limit(1)
        )
        return self.session.execute(query).scalar_one_or_none()

    def upsert_assistant_for_request(
        self,
        *,
        session_id: int,
        request_id: int,
        user_id: str,
        message_type: str,
        text: str | None = None,
        task_snapshot: str | None = None,
        plan_object: str | None = None,
        verifier_decision: str | None = None,
        specialist_result: str | None = None,
    ) -> MessageRecord:
        record = self.get_assistant_for_request(request_id=request_id, user_id=user_id)
        if record is None:
            return self.create(
                session_id=session_id,
                request_id=request_id,
                user_id=user_id,
                role="assistant",
                message_type=message_type,
                text=text,
                task_snapshot=task_snapshot,
                plan_object=plan_object,
                verifier_decision=verifier_decision,
                specialist_result=specialist_result,
            )
        record.message_type = message_type
        record.text = text
        record.task_snapshot = task_snapshot
        record.plan_object = plan_object
        record.verifier_decision = verifier_decision
        record.specialist_result = specialist_result
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_for_session(self, session_id: int, user_id: str) -> list[MessageRecord]:
        query = (
            select(MessageRecord)
            .where(
                MessageRecord.session_id == session_id,
                MessageRecord.user_id == user_id,
            )
            .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
        )
        return list(self.session.execute(query).scalars())

    def list_for_sessions(self, session_ids: list[int], user_id: str) -> list[MessageRecord]:
        if not session_ids:
            return []
        query = (
            select(MessageRecord)
            .where(
                MessageRecord.session_id.in_(session_ids),
                MessageRecord.user_id == user_id,
            )
            .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
        )
        return list(self.session.execute(query).scalars())

    def list_recent_for_session(self, session_id: int, user_id: str, limit: int) -> list[MessageRecord]:
        query = (
            select(MessageRecord)
            .where(
                MessageRecord.session_id == session_id,
                MessageRecord.user_id == user_id,
            )
            .order_by(MessageRecord.created_at.desc(), MessageRecord.id.desc())
            .limit(limit)
        )
        return list(reversed(list(self.session.execute(query).scalars())))
