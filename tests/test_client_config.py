from pathlib import Path

import pytest

from chatops.common.config.application_server import ApplicationServerConfig
from chatops.common.config.monitoring_server import MonitoringServerConfig
from chatops.common.config.project_server import ProjectServerConfig
from chatops.common.config.settings import AppConfig, BedrockConfig, DatabaseConfig, resolve_env_file
from chatops.infra.client.fake_application_impl import FakeApplicationClientImpl
from chatops.infra.client.fake_monitoring_impl import FakeMonitoringClientImpl
from chatops.infra.client.fake_project_impl import FakeProjectClientImpl


def test_server_configs_have_expected_defaults() -> None:
    app_config = AppConfig(_env_file=None)
    db_config = DatabaseConfig(_env_file=None)
    bedrock_config = BedrockConfig(_env_file=None)
    project_server = ProjectServerConfig(_env_file=None)
    application_server = ApplicationServerConfig(_env_file=None)
    monitoring_server = MonitoringServerConfig(_env_file=None)

    assert app_config.request_stream_keepalive_seconds == 15
    assert app_config.approval_ttl_seconds == 900
    assert db_config.url.startswith("postgresql")
    assert bedrock_config.model_id == "amazon.nova-2-lite-v1:0"
    assert bedrock_config.region == "us-east-1"
    assert project_server.SERVER_BASE_URL == "http://localhost:8001"
    assert application_server.SERVER_BASE_URL == "http://localhost:8003"
    assert monitoring_server.SERVER_BASE_URL == "http://localhost:8001"


def test_resolve_env_file_prefers_vault_path(tmp_path: Path) -> None:
    vault_file = tmp_path / "vault.env"
    local_file = tmp_path / ".env"
    vault_file.write_text("BEDROCK_MODEL_ID=vault\n", encoding="utf-8")
    local_file.write_text("BEDROCK_MODEL_ID=local\n", encoding="utf-8")

    resolved = resolve_env_file(vault_path=vault_file, project_root=tmp_path)

    assert resolved == vault_file


def test_bedrock_config_reads_bedrock_prefixed_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0\nBEDROCK_REGION=ap-northeast-2\n",
        encoding="utf-8",
    )

    bedrock_config = BedrockConfig(_env_file=env_file)

    assert bedrock_config.model_id == "anthropic.claude-3-haiku-20240307-v1:0"
    assert bedrock_config.region == "ap-northeast-2"


@pytest.mark.anyio
async def test_fake_clients_return_predictable_payloads() -> None:
    project_client = FakeProjectClientImpl()
    application_client = FakeApplicationClientImpl()
    monitoring_client = FakeMonitoringClientImpl()

    create_result = await project_client.create_project(
        user_id="1",
        role="admin",
        body={"name": "demo"},
    )
    assert create_result["summary"] == "project.create"
    assert create_result["success"] is True
    assert create_result["data"]["name"] == "demo"
    assert await project_client.list_projects(user_id="1", role="admin") == {
        "summary": "demo",
        "items": [
            {
                "id": create_result["data"]["id"],
                "name": "demo",
                "my_role": "OWNER",
            }
        ],
    }
    app_create_result = await application_client.create_apps(
        user_id="1",
        role="admin",
        body={"name": "demo", "project_id": 1},
    )
    assert app_create_result["summary"] == "application.create_apps"
    assert app_create_result["data"]["name"] == "demo"
    assert app_create_result["data"]["project_id"] == 1
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
