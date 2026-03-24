from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from chatops.common.config.settings import resolve_env_file
from chatops.common.config.user_server import get_user_server_config
from chatops.core.client.user import UserClient
from chatops.infra.client.fake_user_impl import FakeUserClientImpl
from chatops.infra.client.user_impl import UserClientImpl


class _FakeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    use_fake_user_client: bool = False


@lru_cache(maxsize=1)
def _get_fake_config() -> _FakeConfig:
    return _FakeConfig()


def get_user_client() -> UserClient:
    if _get_fake_config().use_fake_user_client:
        return FakeUserClientImpl()
    return UserClientImpl(config=get_user_server_config())
