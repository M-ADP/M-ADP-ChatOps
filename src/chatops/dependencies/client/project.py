from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from chatops.common.config.project_server import get_project_server_config
from chatops.common.config.settings import resolve_env_file
from chatops.core.client.project import ProjectClient
from chatops.infra.client.fake_project_impl import FakeProjectClientImpl
from chatops.infra.client.project_impl import ProjectClientImpl


class _FakeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    use_fake_project_client: bool = False


@lru_cache(maxsize=1)
def _get_fake_config() -> _FakeConfig:
    return _FakeConfig()


def get_project_client() -> ProjectClient:
    if _get_fake_config().use_fake_project_client:
        return FakeProjectClientImpl()
    return ProjectClientImpl(config=get_project_server_config())

