from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from chatops.common.config.monitoring_server import MonitoringServerConfig
from chatops.infra.client.monitoring_impl import MonitoringClientImpl


def _response(status: int, payload):
    return SimpleNamespace(
        status=status,
        json=AsyncMock(return_value=payload),
        text=AsyncMock(return_value=""),
    )


def test_monitoring_client_returns_friendly_summary_on_success() -> None:
    http_client = AsyncMock()
    http_client.get.return_value = _response(
        200,
        {
            "data": {
                "app_deployment_traffic": {
                    "app_deployment": {
                        "name": "api-server",
                        "cpu_usage_percentage": 42,
                        "current_instance": 2,
                        "available_instances": 3,
                    },
                    "traffic": {
                        "series": [{"timestamp": "2026-03-28T10:00:00+09:00", "value": 17.5}],
                    },
                },
            },
        },
    )
    client = MonitoringClientImpl(
        config=MonitoringServerConfig(_env_file=None),
        http_client=http_client,
    )

    result = asyncio.run(
        client.get_app_deployment_traffic(
            user_id="user-1",
            role="MEMBER",
            project_id=98,
            app_deployment_name="api-server",
        )
    )

    assert result["success"] is True
    assert "api-server" in result["summary"]
    assert "CPU 42%" in result["summary"]
    assert "17.5" in result["summary"]


def test_monitoring_client_maps_error_to_user_friendly_summary() -> None:
    http_client = AsyncMock()
    http_client.get.return_value = _response(
        503,
        {"message": "temporarily unavailable"},
    )
    client = MonitoringClientImpl(
        config=MonitoringServerConfig(_env_file=None),
        http_client=http_client,
    )

    result = asyncio.run(
        client.get_app_deployment_traffic(
            user_id="user-1",
            role="MEMBER",
            project_id=98,
            app_deployment_name="api-server",
        )
    )

    assert result["success"] is False
    assert "일시적" in result["summary"]
    assert result["status_code"] == 503


def test_monitoring_client_passes_time_window_query_params() -> None:
    http_client = AsyncMock()
    http_client.get.return_value = _response(200, {"data": {"app_deployment_traffic": {}}})
    client = MonitoringClientImpl(
        config=MonitoringServerConfig(_env_file=None),
        http_client=http_client,
    )

    asyncio.run(
        client.get_app_deployment_traffic(
            user_id="user-1",
            role="MEMBER",
            project_id=98,
            app_deployment_name="api-server",
            start="2026-03-28T09:00:00+09:00",
            end="2026-03-28T10:00:00+09:00",
        )
    )

    http_client.get.assert_awaited_once_with(
        "/monitoring/app-deployment/98/api-server",
        params={"start": "2026-03-28T09:00:00+09:00", "end": "2026-03-28T10:00:00+09:00"},
        headers={"X-User-Id": "user-1", "X-User-Role": "MEMBER"},
    )
