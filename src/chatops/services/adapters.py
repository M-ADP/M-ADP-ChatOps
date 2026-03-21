from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class AdapterResult:
    success: bool
    normalized_result: dict[str, Any] | None
    raw_response: dict[str, Any] | str | None
    error_type: str | None
    error_message: str | None


class DownstreamAdapterService:
    def __init__(self, client: httpx.Client | None = None, base_url: str = "") -> None:
        self.client = client or httpx.Client(base_url=base_url)

    def execute(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> AdapterResult:
        try:
            response = self.client.request(
                method=method,
                url=path,
                headers=headers,
                json=json_body,
                params=params,
            )
        except httpx.TimeoutException as exc:
            return AdapterResult(
                success=False,
                normalized_result=None,
                raw_response=None,
                error_type="timeout",
                error_message=str(exc),
            )

        raw_response = self._extract_response_body(response)
        if 200 <= response.status_code < 300:
            normalized_result = raw_response if isinstance(raw_response, dict) else {"text": str(raw_response)}
            return AdapterResult(
                success=True,
                normalized_result=normalized_result,
                raw_response=raw_response,
                error_type=None,
                error_message=None,
            )

        return AdapterResult(
            success=False,
            normalized_result=None,
            raw_response=raw_response,
            error_type=self._normalize_error_type(response.status_code),
            error_message=self._extract_error_message(raw_response),
        )

    def execute_query(self, operation, user_id: str) -> dict[str, Any]:
        result = self.execute(
            method=operation.method,
            path=operation.path,
            headers={"X-User-Id": user_id},
        )
        if result.success:
            return result.normalized_result or {}
        return {"summary": result.error_message or result.error_type or "downstream_error"}

    def _extract_response_body(self, response: httpx.Response) -> dict[str, Any] | str:
        try:
            return response.json()
        except ValueError:
            return response.text

    def _extract_error_message(self, raw_response: dict[str, Any] | str | None) -> str | None:
        if isinstance(raw_response, dict):
            detail = raw_response.get("detail")
            if isinstance(detail, str):
                return detail
        if isinstance(raw_response, str) and raw_response:
            return raw_response
        return None

    def _normalize_error_type(self, status_code: int) -> str:
        if status_code in {401, 403}:
            return "permission_denied"
        if status_code in {400, 422}:
            return "bad_request"
        if status_code == 404:
            return "not_found"
        if status_code >= 500:
            return "downstream_unavailable"
        return "downstream_error"
