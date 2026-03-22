from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Header
from sqlalchemy.orm import Session, sessionmaker

from chatops.config import Settings, get_settings
from chatops.db.session import build_session_factory
from chatops.graph.service import GraphService
from chatops.schemas.auth import AuthContext
from chatops.services.adapters import DownstreamAdapterService
from chatops.services.auth import build_auth_context
from chatops.services.llm import GroqLLMService
from chatops.services.registry import RegistryService
from chatops.services.resolver import ParameterResolverService


@lru_cache(maxsize=1)
def get_app_settings() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return build_session_factory(get_app_settings().database_url)


@lru_cache(maxsize=1)
def get_registry_service() -> RegistryService:
    root = Path(__file__).resolve().parents[3] / "ai_registry"
    return RegistryService.from_directory(root)


@lru_cache(maxsize=1)
def get_llm_service() -> GroqLLMService:
    settings = get_app_settings()
    return GroqLLMService(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        timeout_seconds=settings.downstream_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_graph_service() -> GraphService:
    settings = get_app_settings()
    return GraphService(
        llm_service=get_llm_service(),
        registry_service=get_registry_service(),
        adapter_service=DownstreamAdapterService(
            resource_server_base_url=settings.resource_server_base_url,
            application_server_base_url=settings.application_server_base_url,
            user_server_base_url=settings.user_server_base_url,
            timeout_seconds=settings.downstream_timeout_seconds,
            use_fake=settings.use_fake_downstream_client,
        ),
        resolver_service=ParameterResolverService(),
        database_url=settings.database_url,
    )


def get_db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_auth_context(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
) -> AuthContext:
    return build_auth_context(
        user_id=x_user_id,
        request_id=x_request_id,
        user_role=x_user_role,
        org_id=x_org_id,
    )
