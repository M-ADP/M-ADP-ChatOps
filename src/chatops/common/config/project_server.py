from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chatops.common.config.settings import LoggedSettings, register_config, resolve_env_file


class ProjectServerConfig(LoggedSettings):
    model_config = SettingsConfigDict(
        env_prefix="PROJECT_",
        extra="ignore",
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
    )

    SERVER_BASE_URL: str = "http://localhost:8001"


@register_config
@lru_cache(maxsize=1)
def get_project_server_config() -> ProjectServerConfig:
    return ProjectServerConfig()

