from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from chatops.db.base import Base
from chatops.db.session import build_engine


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    database_path = tmp_path / "chatops-test.db"
    engine = build_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
