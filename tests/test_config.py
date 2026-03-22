from pathlib import Path

import pytest
from pydantic import ValidationError

from chatops.config import Settings, resolve_env_file


def test_settings_have_required_defaults() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/madp_chatops",
        groq_api_key="test-groq-api-key",
    )

    assert settings.api_prefix == "/api/v1"
    assert settings.resource_server_base_url == "http://localhost:8001"
    assert settings.application_server_base_url == "http://localhost:8003"
    assert settings.user_server_base_url == "http://localhost:8002"
    assert settings.use_fake_downstream_client is True
    assert settings.request_stream_keepalive_seconds == 15
    assert settings.approval_ttl_seconds == 900


def test_settings_require_database_url_and_groq_api_key() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_resolve_env_file_prefers_vault_path(tmp_path: Path) -> None:
    vault_file = tmp_path / "vault.env"
    local_file = tmp_path / ".env"
    vault_file.write_text("GROQ_API_KEY=vault\n", encoding="utf-8")
    local_file.write_text("GROQ_API_KEY=local\n", encoding="utf-8")

    resolved = resolve_env_file(vault_path=vault_file, project_root=tmp_path)

    assert resolved == vault_file


def test_resolve_env_file_falls_back_to_project_root(tmp_path: Path) -> None:
    resolved = resolve_env_file(
        vault_path=tmp_path / "missing.env",
        project_root=tmp_path,
    )

    assert resolved == tmp_path / ".env"
