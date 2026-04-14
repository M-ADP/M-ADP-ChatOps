from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chatops.config import resolve_env_file
from chatops.common.config.settings import normalize_database_url
from chatops.db.base import Base
from chatops.db import models  # noqa: F401


class MigrationSettings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file(project_root=ROOT)),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def resolve_database_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return normalize_database_url(configured_url)

    try:
        return normalize_database_url(MigrationSettings().database_url)
    except ValidationError as exc:
        raise RuntimeError("DATABASE_URL 설정이 필요합니다.") from exc


config.set_main_option("sqlalchemy.url", resolve_database_url())
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
