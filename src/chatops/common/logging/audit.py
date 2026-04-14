from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


http_logger = logging.getLogger("chatops.http")
action_logger = logging.getLogger("chatops.actions")


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    return request.client.host if request.client else None


def build_audit_payload(
    request: Request,
    *,
    category: str,
    status_code: int,
    duration_ms: float,
    action: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": "audit",
        "category": category,
        "action": action,
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "status_code": status_code,
        "duration_ms": duration_ms,
        "user_id": request.headers.get("X-User-Id"),
        "user_role": request.headers.get("X-User-Role"),
        "client_ip": _client_ip(request),
        "correlation_id": request.headers.get("X-Request-Id"),
        "session_id": request.path_params.get("session_id"),
        "request_id": request.path_params.get("request_id"),
        "content_type": request.headers.get("content-type"),
        "content_length": request.headers.get("content-length"),
        "error": error,
    }
    return {key: value for key, value in payload.items() if value is not None}


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = perf_counter()
        status_code = 500
        error: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            status_code = int(getattr(exc, "status_code", 500))
            error = type(exc).__name__
            raise
        finally:
            payload = build_audit_payload(
                request,
                category="http",
                action=getattr(request.scope.get("endpoint"), "__name__", None),
                status_code=status_code,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
                error=error,
            )
            http_logger.info("http_audit %s", json.dumps(payload, ensure_ascii=False))


class AuditRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def audited_handler(request: Request) -> Response:
            started_at = perf_counter()
            status_code = 500
            error: str | None = None
            try:
                response = await original_handler(request)
                status_code = response.status_code
                return response
            except Exception as exc:
                status_code = int(getattr(exc, "status_code", 500))
                error = type(exc).__name__
                raise
            finally:
                payload = build_audit_payload(
                    request,
                    category="action",
                    action=self.endpoint.__name__,
                    status_code=status_code,
                    duration_ms=round((perf_counter() - started_at) * 1000, 2),
                    error=error,
                )
                action_logger.info("action_audit %s", json.dumps(payload, ensure_ascii=False))

        return audited_handler
