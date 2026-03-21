import pytest
from pydantic import ValidationError

from chatops.config import Settings


def test_settings_have_required_defaults() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/madp_chatops",
        groq_api_key="test-groq-api-key",
    )

    assert settings.api_prefix == "/api/v1"
    assert settings.request_stream_keepalive_seconds == 15
    assert settings.approval_ttl_seconds == 900


def test_settings_require_database_url_and_groq_api_key() -> None:
    with pytest.raises(ValidationError):
        Settings()
