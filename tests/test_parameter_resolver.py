from __future__ import annotations

from chatops.services.registry import RegistryEntry
from chatops.services.resolver import ParameterResolverService


def test_resolve_application_create_body_from_key_value_message() -> None:
    entry = RegistryEntry(
        id="application.create_apps",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps",
        method="POST",
        summary="애플리케이션 생성하기",
        capability="애플리케이션 생성하기",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("애플리케이션 생성",),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {
                "required": True,
                "required_fields": ["name", "cpu", "memory", "disk", "project_id", "port"],
            },
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="생성 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "앱 생성 name=demo cpu=1 memory=512 disk=10 project_id=98 port=8080",
    )

    assert resolved == {
        "body": {
            "name": "demo",
            "cpu": 1,
            "memory": 512,
            "disk": 10,
            "project_id": 98,
            "port": 8080,
        }
    }


def test_resolve_monitoring_path_from_message() -> None:
    entry = RegistryEntry(
        id="monitoring.get_app_deployment_traffic",
        source_file="apis/monitoring.yaml",
        operation_id="get_app_deployment_traffic",
        path="/monitoring/app-deployment/{project_id}/{app_deployment_name}",
        method="GET",
        summary="트래픽 조회",
        capability="트래픽 조회",
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=("X-User-Id",),
        required_inputs={
            "headers": [],
            "path": [
                {"name": "project_id", "required": True},
                {"name": "app_deployment_name", "required": True},
            ],
            "query": [],
            "body": None,
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="트래픽 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "project_id=98 app_deployment_name=api-server 트래픽 조회",
    )

    assert resolved == {
        "path": {
            "project_id": 98,
            "app_deployment_name": "api-server",
        }
    }
