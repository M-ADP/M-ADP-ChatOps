from __future__ import annotations

from typing import Any, Protocol


class HttpClient(Protocol):
    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...

    async def post(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...

    async def patch(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...

    async def delete(
        self,
        path: str,
        data: Any = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...
