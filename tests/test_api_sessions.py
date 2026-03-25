from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from chatops.api.dependencies import get_db_session
from chatops.app import create_app
from chatops.db.repositories import SessionRepository
from chatops.schemas.sessions import CreateSessionRequest, SessionResponse
from chatops.services.auth import build_auth_context


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_session_persists_owner(db_session) -> None:
    repo = SessionRepository(db_session)

    session = repo.create(user_id="user-1", title=None)

    assert isinstance(session.id, int)
    assert session.id > 0
    assert session.user_id == "user-1"
    assert session.status == "active"


def test_build_auth_context_requires_x_user_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        build_auth_context(user_id=None)

    assert exc_info.value.status_code == 401


def test_session_schemas_use_api_contract_fields() -> None:
    payload = CreateSessionRequest(title="운영 세션")
    response = SessionResponse(
        session_id=1001,
        user_id="user-1",
        title=payload.title,
        status="active",
    )

    assert payload.model_dump() == {"title": "운영 세션"}
    assert response.model_dump()["session_id"] == 1001


def test_create_session_returns_owned_session(client: TestClient) -> None:
    response = client.post(
        "/sessions",
        headers={"X-User-Id": "user-1"},
        json={"title": "운영 세션"},
    )

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["session_id"], int)
    assert body["user_id"] == "user-1"
    assert body["status"] == "active"
