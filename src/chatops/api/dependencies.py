from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Header
from sqlalchemy.orm import Session, sessionmaker

from chatops.config import Settings, get_settings
from chatops.db.session import build_session_factory
from chatops.graph.service import GraphService
from chatops.schemas.auth import AuthContext
from chatops.services.auth import build_auth_context
from chatops.services.llm import LLMService
from chatops.services.registry import RegistryService


class UnconfiguredLLMService:
    def classify(self, message_text: str) -> dict[str, object]:
        raise RuntimeError("LLM service is not configured")

    def answer_inquiry(self, message_text: str) -> str:
        raise RuntimeError("LLM service is not configured")

    def interpret_query_result(self, message_text: str, raw_result: dict[str, object]) -> str:
        raise RuntimeError("LLM service is not configured")

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        raise RuntimeError("LLM service is not configured")


class UnconfiguredAdapterService:
    def execute_query(self, operation, user_id: str) -> dict[str, object]:
        raise RuntimeError("Adapter service is not configured")


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
def get_graph_service() -> GraphService:
    return GraphService(
        llm_service=UnconfiguredLLMService(),
        registry_service=get_registry_service(),
        adapter_service=UnconfiguredAdapterService(),
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
