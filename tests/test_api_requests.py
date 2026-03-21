import pytest
from sqlalchemy.exc import IntegrityError

from chatops.db.repositories import (
    RequestEventRepository,
    RequestRepository,
    SessionRepository,
)
from chatops.domain.enums import RequestStatus


def test_request_repository_updates_status(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    repo = RequestRepository(db_session)

    request = repo.create(
        session_id=session.id,
        user_id="user-1",
        message_text="프로젝트 생성해줘",
    )
    updated = repo.update_status(request.id, RequestStatus.PENDING_APPROVAL.value)

    assert updated is not None
    assert updated.status == RequestStatus.PENDING_APPROVAL.value


def test_request_event_repository_lists_after_sequence(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="상태 알려줘",
    )
    repo = RequestEventRepository(db_session)

    repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=1,
        event_type="request.created",
        payload="{}",
    )
    second = repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=2,
        event_type="response.completed",
        payload='{"status":"completed"}',
    )

    events = repo.list_after_sequence(request.id, 1)

    assert [event.id for event in events] == [second.id]


def test_request_event_repository_rejects_duplicate_sequence(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="상태 알려줘",
    )
    repo = RequestEventRepository(db_session)

    repo.append(
        request_id=request.id,
        session_id=session.id,
        sequence=1,
        event_type="request.created",
        payload="{}",
    )

    with pytest.raises(IntegrityError):
        repo.append(
            request_id=request.id,
            session_id=session.id,
            sequence=1,
            event_type="response.completed",
            payload='{"status":"completed"}',
        )
