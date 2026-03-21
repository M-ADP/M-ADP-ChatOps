from __future__ import annotations

from typing import Any, TypedDict

from chatops.services.registry import RegistryEntry


class GraphState(TypedDict, total=False):
    request_id: str
    session_id: str
    user_id: str
    user_role: str | None
    org_id: str | None
    message_text: str
    approval_granted: bool
    request_type: str
    request_status: str
    requires_approval: bool
    intent: str
    classification_reason: str
    classification_confidence: float
    route: str
    selected_operation_ids: list[str]
    selected_operation: RegistryEntry | None
    query_result: dict[str, Any] | None
    command_result: dict[str, Any] | None
    final_response: str | None
