from __future__ import annotations

from typing import Any

from aiohttp import ClientResponse, ClientSession, ClientTimeout

from chatops.core.client.http import HttpClient


class AioHttpClient(HttpClient):
    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = ClientTimeout(total=timeout)
        self._default_headers = headers or {}

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
        async with ClientSession(timeout=self._timeout, headers=self._merge_headers(headers)) as session:
            response = await session.get(self._build_url(path), params=params)
            await response.read()
            return response

    async def post(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> ClientResponse:
        async with ClientSession(timeout=self._timeout, headers=self._merge_headers(headers)) as session:
            response = await session.post(self._build_url(path), data=data, json=json)
            await response.read()
            return response

    async def patch(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> ClientResponse:
        async with ClientSession(timeout=self._timeout, headers=self._merge_headers(headers)) as session:
            response = await session.patch(self._build_url(path), data=data, json=json)
            await response.read()
            return response

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> ClientResponse:
        async with ClientSession(timeout=self._timeout, headers=self._merge_headers(headers)) as session:
            response = await session.delete(self._build_url(path), params=params)
            await response.read()
            return response

