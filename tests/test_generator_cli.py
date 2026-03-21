from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


def test_generator_creates_operation_level_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "ai_registry"

    subprocess.run(
        [
            sys.executable,
            "scripts/generate_ai_registry.py",
            "--input-dir",
            "apis",
            "--output-dir",
            str(out_dir),
        ],
        check=True,
    )

    generated = sorted(p.name for p in out_dir.glob("*.ai.yaml"))

    assert "project.create.ai.yaml" in generated
    assert "monitoring.get_app_deployment_traffic.ai.yaml" in generated


def test_generator_preserves_manual_fields(tmp_path: Path) -> None:
    out_dir = tmp_path / "ai_registry"
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = out_dir / "project.create.ai.yaml"
    existing.write_text(
        yaml.safe_dump(
            {
                "id": "project.create",
                "capability": "프로젝트 생성",
                "when_to_use": ["사용자가 새 프로젝트 생성을 요청할 때"],
                "when_not_to_use": ["프로젝트 목록 조회 요청일 때"],
                "examples": ["프로젝트 만들어줘"],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "scripts/generate_ai_registry.py",
            "--input-dir",
            "apis",
            "--output-dir",
            str(out_dir),
        ],
        check=True,
    )

    metadata = yaml.safe_load(existing.read_text(encoding="utf-8"))

    assert metadata["capability"] == "프로젝트 생성"
    assert metadata["when_to_use"] == ["사용자가 새 프로젝트 생성을 요청할 때"]


def test_generator_preserves_manual_safety_fields(tmp_path: Path) -> None:
    out_dir = tmp_path / "ai_registry"
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = out_dir / "project.create.ai.yaml"
    existing.write_text(
        yaml.safe_dump(
            {
                "id": "project.create",
                "usable_in": ["query"],
                "operation_kind": "read",
                "requires_confirmation": False,
                "risk_level": "low",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "scripts/generate_ai_registry.py",
            "--input-dir",
            "apis",
            "--output-dir",
            str(out_dir),
        ],
        check=True,
    )

    metadata = yaml.safe_load(existing.read_text(encoding="utf-8"))

    assert metadata["usable_in"] == ["query"]
    assert metadata["operation_kind"] == "read"
    assert metadata["requires_confirmation"] is False
    assert metadata["risk_level"] == "low"


def test_generator_fails_on_duplicate_canonical_ids(tmp_path: Path) -> None:
    input_dir = tmp_path / "apis"
    output_dir = tmp_path / "ai_registry"
    input_dir.mkdir(parents=True, exist_ok=True)

    (input_dir / "demo.yaml").write_text(
        """
openapi: 3.1.0
info:
  title: Demo
  version: 1.0.0
paths:
  /items:
    get:
      operationId: list_demo_endpoint_items_get
      summary: List Demo Items
      responses:
        '200':
          description: ok
  /items/all:
    get:
      operationId: list_demo_endpoint_items_all_get
      summary: List Demo Items Again
      responses:
        '200':
          description: ok
""".strip(),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/generate_ai_registry.py",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Duplicate canonical id" in completed.stderr
