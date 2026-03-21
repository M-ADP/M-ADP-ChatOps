from chatops.db.repositories import SessionRepository


def test_create_session_persists_owner(db_session) -> None:
    repo = SessionRepository(db_session)

    session = repo.create(user_id="user-1", title=None)

    assert session.user_id == "user-1"
    assert session.status == "active"
