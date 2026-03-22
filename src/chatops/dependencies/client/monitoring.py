from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from chatops.common.config.monitoring_server import get_monitoring_server_config
from chatops.common.config.settings import resolve_env_file
from chatops.core.client.monitoring import MonitoringClient
from chatops.infra.client.fake_monitoring_impl import FakeMonitoringClientImpl
from chatops.infra.client.monitoring_impl import MonitoringClientImpl


class _FakeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    use_fake_monitoring_client: bool = False


@lru_cache(maxsize=1)
def _get_fake_config() -> _FakeConfig:
    return _FakeConfig()


def get_monitoring_client() -> MonitoringClient:
    if _get_fake_config().use_fake_monitoring_client:
        return FakeMonitoringClientImpl()
    return MonitoringClientImpl(config=get_monitoring_server_config())

