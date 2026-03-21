from __future__ import annotations

import httpx

from chatops.services.adapters import DownstreamAdapterService


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
