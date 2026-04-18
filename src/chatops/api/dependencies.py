from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Header
from sqlalchemy.orm import Session, sessionmaker

from chatops.common.config.settings import (
    AppConfig,
    AWSConfig,
    BedrockConfig,
    DatabaseConfig,
    get_app_config,
    get_aws_config,
    get_bedrock_config,
    get_db_config,
)
from chatops.db.session import build_session_factory
from chatops.dependencies.client.application import get_application_client
from chatops.dependencies.client.monitoring import get_monitoring_client
from chatops.dependencies.client.project import get_project_client
from chatops.dependencies.client.user import get_user_client
from chatops.graph.service import GraphService
from chatops.schemas.auth import AuthContext
from chatops.services.auth import build_auth_context
from chatops.services.downstream_dispatcher import DownstreamDispatcher
from chatops.services.llm import BedrockLLMService
from chatops.services.registry import RegistryService
from chatops.services.resolver import ParameterResolverService


@lru_cache(maxsize=1)
def get_app_settings() -> AppConfig:
    return get_app_config()


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseConfig:
    return get_db_config()


@lru_cache(maxsize=1)
def get_bedrock_settings() -> BedrockConfig:
    return get_bedrock_config()


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return build_session_factory(get_database_settings().url)


@lru_cache(maxsize=1)
def get_registry_service() -> RegistryService:
    root = Path(__file__).resolve().parents[3] / "ai_registry"
    app_settings = get_app_settings()
    return RegistryService.from_directory(
        root,
        minimum_score_threshold=app_settings.minimum_score_threshold,
        ambiguity_score_threshold=app_settings.ambiguity_score_threshold,
    )


@lru_cache(maxsize=1)
def get_aws_settings() -> AWSConfig:
    return get_aws_config()


@lru_cache(maxsize=1)
def get_llm_service() -> BedrockLLMService:
    import boto3
    from botocore.config import Config

    app_settings = get_app_settings()
    aws_settings = get_aws_settings()
    bedrock_settings = get_bedrock_settings()
    client = boto3.client(
        "bedrock-runtime",
        region_name=bedrock_settings.region,
        aws_access_key_id=aws_settings.aws_access_key_id,
        aws_secret_access_key=aws_settings.aws_secret_access_key,
        config=Config(
            connect_timeout=app_settings.downstream_timeout_seconds,
            read_timeout=app_settings.downstream_timeout_seconds,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    )
    return BedrockLLMService(
        model_id=bedrock_settings.model_id,
        timeout_seconds=app_settings.downstream_timeout_seconds,
        client=client,
        guardrail_id=bedrock_settings.guardrail_id,
        guardrail_version=bedrock_settings.guardrail_version,
    )


@lru_cache(maxsize=1)
def get_downstream_dispatcher() -> DownstreamDispatcher:
    return DownstreamDispatcher(
        project_client=get_project_client(),
        application_client=get_application_client(),
        monitoring_client=get_monitoring_client(),
        user_client=get_user_client(),
    )


@lru_cache(maxsize=1)
def get_graph_service() -> GraphService:
    app_settings = get_app_settings()
    return GraphService(
        llm_service=get_llm_service(),
        registry_service=get_registry_service(),
        downstream_dispatcher=get_downstream_dispatcher(),
        resolver_service=ParameterResolverService(),
        database_url=get_database_settings().url,
        approval_ttl_seconds=app_settings.approval_ttl_seconds,
    )


def get_db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_auth_context(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> AuthContext:
    return build_auth_context(
        user_id=x_user_id,
        user_role=x_user_role,
    )
