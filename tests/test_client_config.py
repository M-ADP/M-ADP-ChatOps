from pathlib import Path

import pytest

from chatops.common.config.application_server import ApplicationServerConfig
from chatops.common.config.monitoring_server import MonitoringServerConfig
from chatops.common.config.project_server import ProjectServerConfig
from chatops.common.config.settings import AppConfig, DatabaseConfig, GroqConfig, resolve_env_file
from chatops.infra.client.fake_application_impl import FakeApplicationClientImpl
from chatops.infra.client.fake_monitoring_impl import FakeMonitoringClientImpl
from chatops.infra.client.fake_project_impl import FakeProjectClientImpl


def test_server_configs_have_expected_defaults() -> None:
    app_config = AppConfig(_env_file=None)
    db_config = DatabaseConfig(_env_file=None)
    groq_config = GroqConfig(_env_file=None)
    project_server = ProjectServerConfig(_env_file=None)
    application_server = ApplicationServerConfig(_env_file=None)
    monitoring_server = MonitoringServerConfig(_env_file=None)

    assert app_config.api_prefix == "/api/v1"
    assert app_config.request_stream_keepalive_seconds == 15
    assert app_config.approval_ttl_seconds == 900
    assert db_config.url.startswith("postgresql")
    assert groq_config.model == "llama-3.3-70b-versatile"
    assert project_server.SERVER_BASE_URL == "http://localhost:8001"
    assert application_server.SERVER_BASE_URL == "http://localhost:8003"
    assert monitoring_server.SERVER_BASE_URL == "http://localhost:8001"


def test_resolve_env_file_prefers_vault_path(tmp_path: Path) -> None:
    vault_file = tmp_path / "vault.env"
    local_file = tmp_path / ".env"
    vault_file.write_text("GROQ_API_KEY=vault\n", encoding="utf-8")
    local_file.write_text("GROQ_API_KEY=local\n", encoding="utf-8")

    resolved = resolve_env_file(vault_path=vault_file, project_root=tmp_path)

    assert resolved == vault_file


def test_groq_config_reads_groq_prefixed_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GROQ_API_KEY=groq-test-key\nGROQ_MODEL=llama-test\n",
        encoding="utf-8",
    )

    groq_config = GroqConfig(_env_file=env_file)

    assert groq_config.api_key == "groq-test-key"
    assert groq_config.model == "llama-test"


@pytest.mark.anyio
async def test_fake_clients_return_predictable_payloads() -> None:
    project_client = FakeProjectClientImpl()
    application_client = FakeApplicationClientImpl()
    monitoring_client = FakeMonitoringClientImpl()

    assert await project_client.create_project(
        user_id="1",
        role="admin",
        body={"name": "demo"},
    ) == {"summary": "project.create"}
    assert await project_client.list_projects(user_id="1", role="admin") == {
        "summary": "프로젝트 목록이 없습니다.",
        "items": [],
    }
    assert await application_client.create_apps(
        user_id="1",
        role="admin",
        body={"name": "demo", "project_id": 1},
    ) == {"summary": "application.create_apps"}
    assert await monitoring_client.get_app_deployment_traffic(
        user_id="1",
        role="admin",
        project_id=98,
        app_deployment_name="api-server",
    ) == {
        "summary": "현재 앱 트래픽 상태는 downstream 연동 전입니다.",
        "project_id": 98,
        "app_deployment_name": "api-server",
    }
