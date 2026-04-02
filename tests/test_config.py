from pathlib import Path

import pytest
from pydantic import ValidationError

from chatops.common.config.application_server import ApplicationServerConfig
from chatops.common.config.project_server import ProjectServerConfig
from chatops.common.config.settings import AppConfig, DatabaseConfig, GroqConfig
from chatops.common.config.user_server import UserServerConfig
from chatops.config import Settings, resolve_env_file
from chatops.infra.client.asyncio_http import AioHttpClient


def test_settings_have_required_defaults() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/madp_chatops",
        groq_api_key="test-groq-api-key",
    )

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


def test_legacy_settings_bridge_common_config_components() -> None:
    settings = Settings.from_components(
        app_config=AppConfig(_env_file=None),
        db_config=DatabaseConfig(_env_file=None),
        groq_config=GroqConfig(_env_file=None),
        project_server=ProjectServerConfig(_env_file=None),
        user_server=UserServerConfig(_env_file=None),
        application_server=ApplicationServerConfig(_env_file=None),
    )

    assert settings.database_url.startswith("postgresql")
    assert settings.groq_model == "llama-3.3-70b-versatile"
    assert settings.resource_server_base_url == "http://localhost:8001"
    assert settings.user_server_base_url == "http://localhost:8002"
    assert settings.application_server_base_url == "http://localhost:8003"


def test_requirements_include_runtime_dependencies() -> None:
    lines = {
        line.strip()
        for line in (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert "fastapi>=0.135.1" in lines
    assert "aiohttp>=3.13.3" in lines
    assert "langgraph>=1.1.3" in lines
    assert "sonyflake-py>=1.3.0" in lines


def test_downstream_http_policy_defaults_are_consistent() -> None:
    client = AioHttpClient(base_url="http://example.test")

    assert client._timeout.total == 10
    assert client._retry_attempts == 1
    assert client._retry_backoff_seconds == 0.5
