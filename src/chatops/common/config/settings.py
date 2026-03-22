from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from pydantic_settings import BaseSettings, SettingsConfigDict

from chatops.common.const.vault import VAULT_ENV_FILE

logger = logging.getLogger(__name__)

_CONFIG_GETTERS: list[Callable[[], BaseSettings]] = []


def resolve_env_file(
    vault_path: Path = Path(VAULT_ENV_FILE),
    project_root: Path | None = None,
) -> Path:
    if vault_path.exists():
        return vault_path

    root = project_root or Path(__file__).resolve().parents[4]
    return root / ".env"


def register_config(fn: Callable[[], BaseSettings]) -> Callable[[], BaseSettings]:
    _CONFIG_GETTERS.append(fn)
    return fn


def load_all_configs() -> None:
    for getter in _CONFIG_GETTERS:
        getter()


class LoggedSettings(BaseSettings):
    def model_post_init(self, __context: Any) -> None:
        fields_info = {name: getattr(self, name) for name in type(self).model_fields}
        logger.info("[Config Loaded] %s -> %s", self.__class__.__name__, fields_info)


class AppConfig(LoggedSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    api_prefix: str = "/api/v1"
    request_stream_keepalive_seconds: int = 15
    approval_ttl_seconds: int = 900
    downstream_timeout_seconds: int = 10


class DatabaseConfig(LoggedSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/madp_chatops"

    @property
    def url(self) -> str:
        return self.database_url


class GroqConfig(LoggedSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    api_key: str = "test-groq-api-key"
    model: str = "llama-3.3-70b-versatile"


class SonyflakeConfig(LoggedSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="SONYFLAKE_",
        extra="ignore",
    )

    machine_id: int = 0


@register_config
@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    return AppConfig()


@register_config
@lru_cache(maxsize=1)
def get_db_config() -> DatabaseConfig:
    return DatabaseConfig()


@register_config
@lru_cache(maxsize=1)
def get_groq_config() -> GroqConfig:
    return GroqConfig()


@register_config
@lru_cache(maxsize=1)
def get_sonyflake_config() -> SonyflakeConfig:
    return SonyflakeConfig()
