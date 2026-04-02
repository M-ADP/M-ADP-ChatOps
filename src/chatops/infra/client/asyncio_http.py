from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from chatops.core.client.http import HttpClient


class AioHttpClient(HttpClient):
    def __init__(
        self,
        base_url: str = "",
        timeout: float = 10.0,
        headers: dict[str, str] | None = None,
        retry_attempts: int = 1,
        retry_backoff_seconds: float = 0.5,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = ClientTimeout(total=timeout)
        self._default_headers = headers or {}
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

    def _build_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    def _merge_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        merged = self._default_headers.copy()
        if headers:
            merged.update(headers)
        return merged

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> ClientResponse:
        return await self._request("get", path, params=params, headers=headers)

    async def post(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> ClientResponse:
        return await self._request("post", path, data=data, json=json, headers=headers)

    async def patch(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> ClientResponse:
        return await self._request("patch", path, data=data, json=json, headers=headers)

    async def delete(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> ClientResponse:
        return await self._request("delete", path, data=data, json=json, params=params, headers=headers)

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> ClientResponse:
        last_error: Exception | None = None
        request_kwargs = dict(kwargs)
        headers = request_kwargs.pop("headers", None)
        for attempt in range(self._retry_attempts + 1):
            try:
                async with ClientSession(timeout=self._timeout, headers=self._merge_headers(headers)) as session:
                    response = await getattr(session, method)(self._build_url(path), **request_kwargs)
                    await response.read()
                if response.status >= 500 and attempt < self._retry_attempts:
                    await asyncio.sleep(self._retry_backoff_seconds)
                    continue
                return response
            except (asyncio.TimeoutError, ClientError) as exc:
                last_error = exc
                if attempt >= self._retry_attempts:
                    raise
                await asyncio.sleep(self._retry_backoff_seconds)
        if last_error is not None:
            raise last_error
        raise RuntimeError("HTTP 요청 실행에 실패했습니다.")
