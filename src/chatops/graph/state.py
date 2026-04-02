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
    approval_granted: bool | str
    request_type: str
    request_status: str
    requires_approval: bool
    intent: str
    classification_reason: str
    classification_confidence: float
    selected_specialist: str | None
    policy_decision: dict[str, Any] | None
    retry_count: int
    route: str
    selected_operation_ids: list[str]
    selected_operation_id: str | None
    missing_inputs: list[str]
    resolved_inputs: dict[str, Any] | None
    query_result: dict[str, Any] | None
    command_result: dict[str, Any] | None
    resolved_references: dict[str, Any] | None
    final_response: str | None
    # P0: Ambiguity detection
    is_ambiguous: bool
    ambiguity_candidates: list[dict[str, Any]]
    clarification_question: str | None
    # P0: TTL tracking
    created_at: str | None
    expires_at: str | None
    # P1: Pre-check
    precheck_passed: bool
    resolved_ids: dict[str, Any] | None
    precheck_error: str | None
    # P1: Risk-level UX
    risk_level: str | None
    # P0: Error code for structured error responses
    error_code: str | None
    # P2: Structured observability
    clarification_type: str | None
    fallback_used: bool
    execution_audit: dict[str, Any] | None
    task_snapshot: dict[str, Any] | None
    plan_object: dict[str, Any] | None
    verifier_decision: dict[str, Any] | None
    specialist_result: dict[str, Any] | None
    session_summary: dict[str, Any] | None
