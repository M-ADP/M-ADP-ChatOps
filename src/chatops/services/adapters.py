from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from chatops.services.registry import RegistryEntry


@dataclass(frozen=True)
class AdapterResult:
    success: bool
    normalized_result: dict[str, Any] | None
    raw_response: dict[str, Any] | str | None
    error_type: str | None
    error_message: str | None


class DownstreamAdapterService:
    def __init__(
        self,
        client: httpx.Client | None = None,
        base_url: str = "",
        resource_server_base_url: str = "",
        application_server_base_url: str = "",
        user_server_base_url: str = "",
        timeout_seconds: float = 10.0,
        client_factory: Callable[[str], httpx.Client] | None = None,
        use_fake: bool = True,
    ) -> None:
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self.resource_server_base_url = resource_server_base_url
        self.application_server_base_url = application_server_base_url
        self.user_server_base_url = user_server_base_url
        self.client_factory = client_factory or (
            lambda resolved_base_url: httpx.Client(base_url=resolved_base_url, timeout=timeout_seconds)
        )
        self.use_fake = use_fake
        self._clients: dict[str, httpx.Client] = {}

    def execute(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        client: httpx.Client | None = None,
    ) -> AdapterResult:
        http_client = client or self.client
        try:
            response = http_client.request(
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

    def execute_operation(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> AdapterResult:
        if self.use_fake:
            summary = f"{operation.id} downstream 연동 전 ({user_id})"
            return AdapterResult(
                success=True,
                normalized_result={"summary": summary},
                raw_response={"summary": summary},
                error_type=None,
                error_message=None,
            )

        inputs = resolved_inputs or {}
        missing_inputs = self._find_missing_inputs(
            operation=operation,
            user_id=user_id,
            user_role=user_role,
            org_id=org_id,
            resolved_inputs=inputs,
        )
        if missing_inputs:
            return AdapterResult(
                success=False,
                normalized_result=None,
                raw_response=None,
                error_type="bad_request",
                error_message=f"missing required inputs: {', '.join(missing_inputs)}",
            )

        headers = self._build_headers(
            operation=operation,
            user_id=user_id,
            user_role=user_role,
            org_id=org_id,
            resolved_inputs=inputs,
        )
        path = self._build_path(operation.path, inputs.get("path", {}))
        params = inputs.get("query")
        json_body = inputs.get("body")
        return self.execute(
            method=operation.method,
            path=path,
            headers=headers,
            json_body=json_body,
            params=params,
            client=self._client_for_operation(operation),
        )

    def execute_query(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.execute_operation(
            operation=operation,
            user_id=user_id,
            user_role=user_role,
            org_id=org_id,
            resolved_inputs=resolved_inputs,
        )
        if result.success:
            return result.normalized_result or {}
        return {"summary": result.error_message or result.error_type or "downstream_error"}

    def execute_command(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.execute_operation(
            operation=operation,
            user_id=user_id,
            user_role=user_role,
            org_id=org_id,
            resolved_inputs=resolved_inputs,
        )
        if result.success:
            normalized_result = result.normalized_result or {}
            summary = normalized_result.get("summary") if isinstance(normalized_result, dict) else None
            return {
                "success": True,
                "summary": summary or operation.id,
                "result": normalized_result,
            }
        return {
            "success": False,
            "summary": result.error_message or result.error_type or "downstream_error",
            "error_type": result.error_type,
        }

    def _client_for_operation(self, operation: RegistryEntry) -> httpx.Client:
        if not any(
            [self.resource_server_base_url, self.application_server_base_url, self.user_server_base_url]
        ):
            return self.client

        base_url = self._resolve_base_url(operation)
        if base_url not in self._clients:
            self._clients[base_url] = self.client_factory(base_url)
        return self._clients[base_url]

    def _resolve_base_url(self, operation: RegistryEntry) -> str:
        source_name = Path(operation.source_file).name
        if source_name == "application.yaml":
            return self.application_server_base_url
        if source_name in {"project.yaml", "monitoring.yaml"}:
            return self.resource_server_base_url
        return self.user_server_base_url

    def _build_headers(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None,
        org_id: str | None,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, str]:
        available_headers = {
            "X-User-Id": user_id,
            "X-User-Role": user_role,
            "X-Org-Id": org_id,
        }
        headers: dict[str, str] = {}
        for header_name in operation.required_headers:
            header_value = available_headers.get(header_name)
            if header_value is not None:
                headers[header_name] = str(header_value)

        for item in resolved_inputs.get("headers", []):
            headers[str(item["name"])] = str(item["value"])
        return headers

    def _find_missing_inputs(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None,
        org_id: str | None,
        resolved_inputs: dict[str, Any],
    ) -> list[str]:
        missing: list[str] = []
        available_headers = {
            "X-User-Id": user_id,
            "X-User-Role": user_role,
            "X-Org-Id": org_id,
        }
        for header_name in operation.required_headers:
            if available_headers.get(header_name) is None:
                missing.append(f"header.{header_name}")

        provided_path = resolved_inputs.get("path", {})
        for item in operation.required_inputs.get("path", []):
            if item.get("required") and provided_path.get(item["name"]) is None:
                missing.append(f"path.{item['name']}")

        provided_query = resolved_inputs.get("query", {})
        for item in operation.required_inputs.get("query", []):
            if item.get("required") and provided_query.get(item["name"]) is None:
                missing.append(f"query.{item['name']}")

        body = operation.required_inputs.get("body")
        provided_body = resolved_inputs.get("body", {})
        if isinstance(body, dict) and body.get("required"):
            required_fields = body.get("required_fields", [])
            if required_fields:
                for field_name in required_fields:
                    if provided_body.get(field_name) is None:
                        missing.append(f"body.{field_name}")
            elif not provided_body:
                missing.append("body")

        return missing

    def _build_path(self, raw_path: str, path_values: dict[str, Any]) -> str:
        resolved = raw_path
        for key, value in path_values.items():
            resolved = resolved.replace(f"{{{key}}}", str(value))
        return resolved

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
