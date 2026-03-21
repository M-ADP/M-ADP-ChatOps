from sqlalchemy import select
from sqlalchemy.orm import Session

from chatops.db.models import RequestEventRecord, RequestRecord, SessionRecord
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

    def get_for_user(self, session_id: str, user_id: str) -> SessionRecord | None:
        query = select(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.user_id == user_id,
        )
        return self.session.execute(query).scalar_one_or_none()


class RequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        session_id: str,
        user_id: str,
        message_text: str,
        request_type: str | None = None,
        requires_approval: bool = False,
    ) -> RequestRecord:
        record = RequestRecord(
            session_id=session_id,
            user_id=user_id,
            message_text=message_text,
            request_type=request_type,
            status=RequestStatus.CREATED.value,
            requires_approval=requires_approval,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_for_user(self, request_id: str, user_id: str) -> RequestRecord | None:
        query = select(RequestRecord).where(
            RequestRecord.id == request_id,
            RequestRecord.user_id == user_id,
        )
        return self.session.execute(query).scalar_one_or_none()

    def update_status(self, request_id: str, status: str) -> RequestRecord | None:
        record = self.session.get(RequestRecord, request_id)
        if record is None:
            return None
        record.status = status
        self.session.commit()
        self.session.refresh(record)
        return record


class RequestEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        request_id: str,
        session_id: str,
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

    def list_after_sequence(self, request_id: str, sequence: int) -> list[RequestEventRecord]:
        query = (
            select(RequestEventRecord)
            .where(
                RequestEventRecord.request_id == request_id,
                RequestEventRecord.sequence > sequence,
            )
            .order_by(RequestEventRecord.sequence.asc())
        )
        return list(self.session.execute(query).scalars())
