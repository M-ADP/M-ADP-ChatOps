from __future__ import annotations

import httpx

from chatops.services.adapters import DownstreamAdapterService
from chatops.services.registry import RegistryEntry


def test_permission_denied_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "forbidden"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.com")
    service = DownstreamAdapterService(client=client)

    result = service.execute(
        method="POST",
        path="/projects",
        headers={"X-User-Id": "user-1"},
        json_body={"name": "demo"},
    )

    assert result.success is False
    assert result.error_type == "permission_denied"


def test_success_response_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "project-1", "name": "demo"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.com")
    service = DownstreamAdapterService(client=client)

    result = service.execute(
        method="GET",
        path="/projects/project-1",
        headers={"X-User-Id": "user-1"},
    )

    assert result.success is True
    assert result.normalized_result == {"id": "project-1", "name": "demo"}
    assert result.error_type is None


def test_timeout_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.com")
    service = DownstreamAdapterService(client=client)

    result = service.execute(
        method="GET",
        path="/monitoring/apps/traffic",
        headers={"X-User-Id": "user-1"},
    )

    assert result.success is False
    assert result.error_type == "timeout"


def test_execute_operation_routes_project_api_to_resource_server() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["user_id"] = request.headers["X-User-Id"]
        seen["user_role"] = request.headers["X-User-Role"]
        return httpx.Response(200, json={"ok": True})

    entry = RegistryEntry(
        id="project.create",
        source_file="apis/project.yaml",
        operation_id="create_project",
        path="/projects",
        method="POST",
        summary="프로젝트 생성",
        capability="프로젝트 생성",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("프로젝트 생성",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="생성 결과",
        plan_template=(),
        examples=(),
    )

    service = DownstreamAdapterService(
        client_factory=lambda base_url: httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url=base_url,
        ),
        resource_server_base_url="https://resource.internal",
        application_server_base_url="https://application.internal",
        user_server_base_url="https://user.internal",
        use_fake=False,
    )

    result = service.execute_operation(
        operation=entry,
        user_id="user-1",
        user_role="admin",
    )

    assert result.success is True
    assert seen["url"] == "https://resource.internal/projects"
    assert seen["user_id"] == "user-1"
    assert seen["user_role"] == "admin"


def test_execute_operation_returns_bad_request_when_required_inputs_missing() -> None:
    entry = RegistryEntry(
        id="project.create",
        source_file="apis/project.yaml",
        operation_id="create_project",
        path="/projects",
        method="POST",
        summary="프로젝트 생성",
        capability="프로젝트 생성",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("프로젝트 생성",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["name"]},
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="생성 결과",
        plan_template=(),
        examples=(),
    )

    service = DownstreamAdapterService(
        resource_server_base_url="https://resource.internal",
        application_server_base_url="https://application.internal",
        user_server_base_url="https://user.internal",
        use_fake=False,
    )

    result = service.execute_operation(
        operation=entry,
        user_id="user-1",
        user_role="admin",
    )

    assert result.success is False
    assert result.error_type == "bad_request"
    assert result.error_message == "missing required inputs: body.name"
