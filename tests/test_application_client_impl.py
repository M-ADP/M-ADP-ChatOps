from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from chatops.common.config.application_server import ApplicationServerConfig
from chatops.infra.client.application_impl import ApplicationClientImpl


def _response(status: int = 200, payload: dict | None = None):
    return SimpleNamespace(
        status=status,
        json=AsyncMock(return_value=payload or {"ok": True}),
        text=AsyncMock(return_value=""),
    )


def test_delete_apps_passes_json_body_to_http_client() -> None:
    http_client = AsyncMock()
    http_client.delete.return_value = _response()
    client = ApplicationClientImpl(
        config=ApplicationServerConfig(SERVER_BASE_URL="http://example.test"),
        http_client=http_client,
    )

    asyncio.run(
        client.delete_apps(
            user_id="user-1",
            role="MEMBER",
            body={"application_id": 777},
        )
    )

    http_client.delete.assert_awaited_once_with(
        "/apps",
        json={"application_id": 777},
        headers={"X-User-Id": "user-1", "X-User-Role": "MEMBER"},
    )
