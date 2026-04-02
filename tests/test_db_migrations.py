from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_head_runs(tmp_path: Path) -> None:
    database_path = tmp_path / "chatops.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env["GROQ_API_KEY"] = "test-groq-api-key"

    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    sessions_columns = {column["name"]: column for column in inspector.get_columns("sessions")}
    requests_columns = {column["name"]: column for column in inspector.get_columns("requests")}
    request_events_columns = {column["name"]: column for column in inspector.get_columns("request_events")}
    messages_columns = {column["name"]: column for column in inspector.get_columns("messages")}

    assert sessions_columns["id"]["type"].python_type is int
    assert "session_summary" in sessions_columns
    assert requests_columns["id"]["type"].python_type is int
    assert requests_columns["session_id"]["type"].python_type is int
    assert "plan_object" in requests_columns
    assert "verifier_decision" in requests_columns
    assert "specialist_result" in requests_columns
    assert request_events_columns["id"]["type"].python_type is int
    assert request_events_columns["request_id"]["type"].python_type is int
    assert request_events_columns["session_id"]["type"].python_type is int
    assert "task_snapshot" in messages_columns
