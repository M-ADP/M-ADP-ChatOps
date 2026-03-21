from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_imports_without_explicit_pythonpath() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DATABASE_URL"] = "sqlite:////tmp/madp_chatops_entrypoint.db"
    env["GROQ_API_KEY"] = "test-groq-api-key"

    completed = subprocess.run(
        [sys.executable, "-c", "import main; print(type(main.app).__name__)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "FastAPI" in completed.stdout
