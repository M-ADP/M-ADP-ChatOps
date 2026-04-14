from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

from chatops.common.const.vault import VAULT_ENV_FILE

logger = logging.getLogger(__name__)

_CONFIG_GETTERS: list[Callable[[], BaseSettings]] = []

DEFAULT_DATABASE_SCHEME = "postgresql+psycopg"
DEFAULT_DATABASE_USER = "postgres"
DEFAULT_DATABASE_PASSWORD = "postgres"
DEFAULT_DATABASE_HOST = "localhost"
DEFAULT_DATABASE_PORT = 5432
DEFAULT_DATABASE_NAME = "madp_chatops"


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


def normalize_database_url(raw_value: str) -> str:
    value = raw_value.strip()
    if "://" in value or value.startswith("sqlite"):
        return value

    host_port, _, database_name = value.partition("/")
    host, separator, port = host_port.partition(":")
    normalized_host = host or DEFAULT_DATABASE_HOST
    normalized_port = int(port) if separator and port else DEFAULT_DATABASE_PORT
    normalized_database = database_name or DEFAULT_DATABASE_NAME
    netloc = (
        f"{DEFAULT_DATABASE_USER}:{DEFAULT_DATABASE_PASSWORD}"
        f"@{normalized_host}:{normalized_port}"
    )
    return urlunsplit(
        (
            DEFAULT_DATABASE_SCHEME,
            netloc,
            f"/{normalized_database}",
            "",
            "",
        )
    )


class LoggedSettings(BaseSettings):
    def model_post_init(self, __context: Any) -> None:
        fields_info = {
            name: self._redact_field(name, getattr(self, name))
            for name in type(self).model_fields
        }
        logger.info("[Config Loaded] %s -> %s", self.__class__.__name__, fields_info)

    @staticmethod
    def _redact_field(name: str, value: Any) -> Any:
        sensitive_tokens = ("key", "secret", "token", "password", "database_url", "url")
        if any(token in name.lower() for token in sensitive_tokens):
            if isinstance(value, str) and "://" in value:
                parts = urlsplit(value)
                if parts.password is not None:
                    username = parts.username or ""
                    netloc = f"{username}:***@{parts.hostname or ''}"
                    if parts.port is not None:
                        netloc = f"{netloc}:{parts.port}"
                    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
            return "***REDACTED***"
        return value


class AppConfig(LoggedSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    request_stream_keepalive_seconds: int = 15
    approval_ttl_seconds: int = 900
    downstream_timeout_seconds: int = 10
    # P0: Ambiguity detection — 상위 2개 후보 점수 차이가 이 값 이하이면 모호
    ambiguity_score_threshold: int = 5
    # P1: 최고 점수가 이 값 미만이면 "지원하지 않는 기능" 처리
    minimum_score_threshold: int = 8


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
        return normalize_database_url(self.database_url)


class BedrockConfig(LoggedSettings):
    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="BEDROCK_",
        extra="ignore",
    )

    model_id: str = "amazon.nova-2-lite-v1:0"
    region: str = "us-east-1"


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
def get_bedrock_config() -> BedrockConfig:
    return BedrockConfig()


@register_config
@lru_cache(maxsize=1)
def get_sonyflake_config() -> SonyflakeConfig:
    return SonyflakeConfig()
