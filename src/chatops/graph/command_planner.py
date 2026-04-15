from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from chatops.domain.enums import RequestStatus
from chatops.graph.state import GraphState
from chatops.services.decision_trace import log_decision_trace


GraphStateFactory = Callable[[Any, GraphState, list[str]], GraphState | None]
MissingInputsResolver = Callable[[Any, dict[str, Any]], list[str]]
AmbiguityResponseBuilder = Callable[[Any], str]
MissingInputResponseBuilder = Callable[[Any, list[str]], str]
RiskAwarePlanBuilder = Callable[[Any, dict[str, Any]], str]


@dataclass(frozen=True)
class CommandPlanningService:
    registry_service: Any
    resolver_service: Any
    auth_precheck_failure: GraphStateFactory
    missing_required_inputs: MissingInputsResolver
    ambiguity_response_builder: AmbiguityResponseBuilder
    missing_input_response_builder: MissingInputResponseBuilder
    precheck_service: Any
    risk_aware_plan_builder: RiskAwarePlanBuilder

    def prepare(self, state: GraphState) -> GraphState:
        effective = state.get("effective_message_text", state["message_text"])
        scored = self.registry_service.find_scored_candidates(effective, usable_in="command")
        operation_ids = [sc.entry.id for sc in scored]
        preferred_operation_id = str(state.get("selected_operation_id") or "").strip()
        selected = None

        if preferred_operation_id:
            selected = self.registry_service.get_entry(preferred_operation_id)
            if selected is None or "command" not in selected.usable_in:
                selected = None
            else:
                if preferred_operation_id not in operation_ids:
                    operation_ids = [preferred_operation_id, *operation_ids]

        if selected is None:
            if not scored:
                log_decision_trace(
                    stage="command_planner",
                    request_id=state.get("request_id"),
                    session_id=state.get("session_id"),
                    user_id=state.get("user_id"),
                    decision="failed",
                    reason="no matching command operation",
                    data={"message_text": effective, "selected_operation_ids": operation_ids},
                )
                return {
                    "selected_operation_id": None,
                    "selected_operation_ids": [],
                    "final_response": "요청하신 기능을 지원하지 않거나, 어떤 작업인지 명확하지 않습니다.",
                    "request_status": RequestStatus.FAILED.value,
                    "requires_approval": False,
                    "error_code": "NO_MATCHING_OPERATION",
                }

            is_ambiguous, ambiguous_candidates = self.registry_service.detect_ambiguity(scored)
            if is_ambiguous:
                log_decision_trace(
                    stage="command_planner",
                    request_id=state.get("request_id"),
                    session_id=state.get("session_id"),
                    user_id=state.get("user_id"),
                    decision="ambiguous",
                    reason="multiple command candidates remained after scoring",
                    data={
                        "message_text": effective,
                        "selected_operation_ids": operation_ids,
                        "ambiguity_candidates": [sc.entry.id for sc in ambiguous_candidates],
                    },
                )
                return {
                    "selected_operation_id": None,
                    "selected_operation_ids": operation_ids,
                    "is_ambiguous": True,
                    "ambiguity_candidates": [
                        {"id": sc.entry.id, "capability": sc.entry.capability, "score": sc.score}
                        for sc in ambiguous_candidates
                    ],
                    "final_response": self.ambiguity_response_builder(ambiguous_candidates),
                    "request_status": RequestStatus.AMBIGUOUS.value,
                    "requires_approval": False,
                    "error_code": "AMBIGUOUS_OPERATION",
                }

            selected = scored[0].entry
        auth_error = self.auth_precheck_failure(selected, state, operation_ids)
        if auth_error is not None:
            return auth_error

        resolved_inputs = self.resolver_service.resolve(
            selected,
            effective,
            session_context=state.get("session_context"),
        )
        missing_inputs = self.missing_required_inputs(selected, resolved_inputs)
        if missing_inputs:
            log_decision_trace(
                stage="command_planner",
                request_id=state.get("request_id"),
                session_id=state.get("session_id"),
                user_id=state.get("user_id"),
                decision="input_required",
                reason="required command inputs are missing",
                data={
                    "message_text": effective,
                    "selected_operation_id": selected.id,
                    "selected_operation_ids": operation_ids,
                    "missing_inputs": missing_inputs,
                },
            )
            return {
                "selected_operation_id": selected.id,
                "selected_operation_ids": operation_ids,
                "resolved_inputs": resolved_inputs,
                "missing_inputs": missing_inputs,
                "final_response": self.missing_input_response_builder(selected, missing_inputs),
                "request_status": RequestStatus.INPUT_REQUIRED.value,
                "requires_approval": False,
                "risk_level": selected.risk_level,
            }

        precheck_result = self.precheck_service.run(
            operation=selected,
            resolved_inputs=resolved_inputs,
            user_id=state["user_id"],
            user_role=state.get("user_role"),
        )
        if precheck_result.get("error"):
            log_decision_trace(
                stage="command_planner",
                request_id=state.get("request_id"),
                session_id=state.get("session_id"),
                user_id=state.get("user_id"),
                decision="failed",
                reason="precheck failed",
                data={
                    "selected_operation_id": selected.id,
                    "selected_operation_ids": operation_ids,
                    "precheck_error": precheck_result["error"],
                },
            )
            return {
                "selected_operation_id": selected.id,
                "selected_operation_ids": operation_ids,
                "resolved_inputs": resolved_inputs,
                "precheck_passed": False,
                "precheck_error": precheck_result["error"],
                "final_response": precheck_result["error"],
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
                "error_code": "PRECHECK_FAILED",
            }
        if precheck_result.get("resolved_ids"):
            resolved_inputs = dict(resolved_inputs)
            resolved_inputs["resolved_ids"] = precheck_result["resolved_ids"]

        log_decision_trace(
            stage="command_planner",
            request_id=state.get("request_id"),
            session_id=state.get("session_id"),
            user_id=state.get("user_id"),
            decision="pending_approval",
            reason="command plan prepared successfully",
            data={
                "message_text": effective,
                "selected_operation_id": selected.id,
                "selected_operation_ids": operation_ids,
                "resolved_ids": precheck_result.get("resolved_ids"),
            },
        )
        return {
            "selected_operation_id": selected.id,
            "selected_operation_ids": operation_ids,
            "resolved_inputs": resolved_inputs,
            "final_response": self.risk_aware_plan_builder(selected, resolved_inputs),
            "request_status": RequestStatus.PENDING_APPROVAL.value,
            "requires_approval": True,
            "risk_level": selected.risk_level,
            "precheck_passed": True,
            "resolved_ids": precheck_result.get("resolved_ids"),
        }
