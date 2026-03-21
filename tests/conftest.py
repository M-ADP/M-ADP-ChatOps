from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Generator
import os

import pytest
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from chatops.db.base import Base
from chatops.db.session import build_engine

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def postgres_dsn() -> str:
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/madp_chatops_test",
    )


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = build_engine("sqlite+pysqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
