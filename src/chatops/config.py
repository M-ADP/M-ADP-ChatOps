from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def resolve_env_file(
    vault_path: Path = Path("/vault/secrets/.env"),
    project_root: Path | None = None,
) -> Path:
    if vault_path.exists():
        return vault_path

    root = project_root or Path(__file__).resolve().parents[2]
    return root / ".env"


class Settings(BaseSettings):
    api_prefix: str = "/api/v1"
    database_url: str
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    request_stream_keepalive_seconds: int = 15
    approval_ttl_seconds: int = 900
    downstream_timeout_seconds: int = 10

    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
