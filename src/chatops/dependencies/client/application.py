from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from chatops.common.config.application_server import get_application_server_config
from chatops.common.config.settings import resolve_env_file
from chatops.core.client.application import ApplicationClient
from chatops.infra.client.application_impl import ApplicationClientImpl
from chatops.infra.client.fake_application_impl import FakeApplicationClientImpl


class _FakeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    use_fake_application_client: bool = False


@lru_cache(maxsize=1)
def _get_fake_config() -> _FakeConfig:
    return _FakeConfig()


def get_application_client() -> ApplicationClient:
    if _get_fake_config().use_fake_application_client:
        return FakeApplicationClientImpl()
    return ApplicationClientImpl(config=get_application_server_config())

