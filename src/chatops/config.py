from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from chatops.common.config.application_server import (
    ApplicationServerConfig,
    get_application_server_config,
)
from chatops.common.config.project_server import ProjectServerConfig, get_project_server_config
from chatops.common.config.settings import (
    AppConfig,
    DatabaseConfig,
    GroqConfig,
    SonyflakeConfig,
    get_app_config,
    get_db_config,
    get_groq_config,
    get_sonyflake_config,
    resolve_env_file,
)
from chatops.common.config.user_server import UserServerConfig, get_user_server_config


class Settings(BaseSettings):
    database_url: str
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    resource_server_base_url: str = "http://localhost:8001"
    user_server_base_url: str = "http://localhost:8002"
    application_server_base_url: str = "http://localhost:8003"
    use_fake_downstream_client: bool = True
    request_stream_keepalive_seconds: int = 15
    approval_ttl_seconds: int = 900
    downstream_timeout_seconds: int = 10

    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    @classmethod
    def from_components(
        cls,
        *,
        app_config: AppConfig,
        db_config: DatabaseConfig,
        groq_config: GroqConfig,
        project_server: ProjectServerConfig,
        user_server: UserServerConfig,
        application_server: ApplicationServerConfig,
    ) -> "Settings":
        return cls.model_validate(
            {
                "database_url": db_config.url,
                "groq_api_key": groq_config.api_key,
                "groq_model": groq_config.model,
                "resource_server_base_url": project_server.SERVER_BASE_URL,
                "user_server_base_url": user_server.SERVER_BASE_URL,
                "application_server_base_url": application_server.SERVER_BASE_URL,
                "request_stream_keepalive_seconds": app_config.request_stream_keepalive_seconds,
                "approval_ttl_seconds": app_config.approval_ttl_seconds,
                "downstream_timeout_seconds": app_config.downstream_timeout_seconds,
            }
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_components(
        app_config=get_app_config(),
        db_config=get_db_config(),
        groq_config=get_groq_config(),
        project_server=get_project_server_config(),
        user_server=get_user_server_config(),
        application_server=get_application_server_config(),
    )


@lru_cache(maxsize=1)
def get_sonyflake_settings() -> SonyflakeConfig:
    return get_sonyflake_config()
