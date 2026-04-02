from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from chatops.domain.enums import RequestStatus
from chatops.graph.state import GraphState


logger = logging.getLogger("chatops.graph.nodes")


class AuditObservabilityService:
    @staticmethod
    def derive_clarification_type(state_update: GraphState) -> str | None:
        request_status = state_update.get("request_status")
        if request_status == RequestStatus.AMBIGUOUS.value:
            return "ambiguity"
        if request_status == RequestStatus.INPUT_REQUIRED.value:
            return "missing_input"
        error_code = state_update.get("error_code")
        if error_code == "AUTH_CONTEXT_MISSING":
            return "auth_context"
        if error_code == "PRECHECK_FAILED":
            return "precheck_failure"
        return None

    def log_clarification_event(
        self,
        *,
        request_id: Any,
        session_id: Any,
        user_id: Any,
        operation_id: str | None,
        clarification_type: str,
    ) -> None:
        payload = self.build_audit_payload(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            operation_id=operation_id,
            latency_ms=None,
            status_code=None,
            fallback_used=False,
            clarification_type=clarification_type,
        )
        logger.info("clarification_event %s", json.dumps(payload, ensure_ascii=False))

    def log_downstream_execution(
        self,
        *,
        request_id: Any,
        session_id: Any,
        user_id: Any,
        operation_id: str,
        result: dict[str, Any],
        started_at: float,
        clarification_type: str | None,
    ) -> dict[str, Any]:
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        status_code = int(result.get("status_code", 200))
        payload = self.build_audit_payload(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            operation_id=operation_id,
            latency_ms=latency_ms,
            status_code=status_code,
            fallback_used=bool(result.get("fallback_used", False)),
            clarification_type=clarification_type,
        )
        logger.info("downstream_execution %s", json.dumps(payload, ensure_ascii=False))
        return payload

    @staticmethod
    def build_audit_payload(
        *,
        request_id: Any,
        session_id: Any,
        user_id: Any,
        operation_id: str | None,
        latency_ms: float | None,
        status_code: int | None,
        fallback_used: bool,
        clarification_type: str | None,
    ) -> dict[str, Any]:
        downstream = operation_id.split(".")[0] if operation_id else None
        return {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "operation": operation_id,
            "latency_ms": latency_ms,
            "downstream": downstream,
            "status_code": status_code,
            "fallback_used": fallback_used,
            "clarification_type": clarification_type,
        }
