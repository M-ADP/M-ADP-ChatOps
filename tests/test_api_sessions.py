import pytest
from fastapi import HTTPException

from chatops.db.repositories import SessionRepository
from chatops.schemas.sessions import CreateSessionRequest, SessionResponse
from chatops.services.auth import build_auth_context


def test_create_session_persists_owner(db_session) -> None:
    repo = SessionRepository(db_session)

    session = repo.create(user_id="user-1", title=None)

    assert session.user_id == "user-1"
    assert session.status == "active"


def test_build_auth_context_requires_x_user_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        build_auth_context(user_id=None)

    assert exc_info.value.status_code == 401


def test_session_schemas_use_api_contract_fields() -> None:
    payload = CreateSessionRequest(title="운영 세션")
    response = SessionResponse(
        session_id="session-1",
        user_id="user-1",
        title=payload.title,
        status="active",
    )

    assert payload.model_dump() == {"title": "운영 세션"}
    assert response.model_dump()["session_id"] == "session-1"
