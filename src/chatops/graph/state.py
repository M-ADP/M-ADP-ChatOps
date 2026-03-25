from __future__ import annotations

from typing import Any, TypedDict

class GraphState(TypedDict, total=False):
    request_id: int
    session_id: int
    user_id: str
    user_role: str | None
    org_id: str | None
    message_text: str
    effective_message_text: str
    session_context: dict[str, Any] | None
    approval_granted: bool
    request_type: str
    request_status: str
    requires_approval: bool
    intent: str
    classification_reason: str
    classification_confidence: float
    route: str
    selected_operation_ids: list[str]
    selected_operation_id: str | None
    missing_inputs: list[str]
    resolved_inputs: dict[str, Any] | None
    query_result: dict[str, Any] | None
    command_result: dict[str, Any] | None
    resolved_references: dict[str, Any] | None
    final_response: str | None
