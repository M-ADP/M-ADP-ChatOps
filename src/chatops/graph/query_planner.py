from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from chatops.domain.enums import RequestStatus
from chatops.graph.state import GraphState


GraphStateFactory = Callable[[Any, GraphState, list[str]], GraphState | None]
MissingInputsResolver = Callable[[Any, dict[str, Any]], list[str]]
ClarificationBuilder = Callable[[Any], str]
MissingInputResponseBuilder = Callable[[str, list[str]], str]


@dataclass(frozen=True)
class QueryPlanningService:
    registry_service: Any
    resolver_service: Any
    auth_precheck_failure: GraphStateFactory
    missing_required_inputs: MissingInputsResolver
    ambiguity_question_builder: ClarificationBuilder
    missing_input_response_builder: MissingInputResponseBuilder

    def prepare(self, state: GraphState) -> GraphState:
        effective = state.get("effective_message_text", state["message_text"])
        scored = self.registry_service.find_scored_candidates(effective, usable_in="query")
        if not scored:
            return {
                "selected_operation_id": None,
                "selected_operation_ids": [],
                "final_response": "요청하신 기능을 지원하지 않거나, 어떤 작업인지 명확하지 않습니다.",
                "request_status": RequestStatus.FAILED.value,
                "error_code": "NO_MATCHING_OPERATION",
            }

        operation_ids = [sc.entry.id for sc in scored]
        is_ambiguous, ambiguous_candidates = self.registry_service.detect_ambiguity(scored)
        if is_ambiguous:
            clarification_question = self.ambiguity_question_builder(ambiguous_candidates)
            return {
                "selected_operation_id": None,
                "selected_operation_ids": operation_ids,
                "is_ambiguous": True,
                "ambiguity_candidates": [
                    {"id": sc.entry.id, "capability": sc.entry.capability, "score": sc.score}
                    for sc in ambiguous_candidates
                ],
                "clarification_question": clarification_question,
                "final_response": clarification_question,
                "request_status": RequestStatus.AMBIGUOUS.value,
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
            clarification_question = self.missing_input_response_builder(selected.id, missing_inputs)
            return {
                "selected_operation_id": selected.id,
                "selected_operation_ids": operation_ids,
                "resolved_inputs": resolved_inputs,
                "missing_inputs": missing_inputs,
                "clarification_question": clarification_question,
                "final_response": clarification_question,
                "request_status": RequestStatus.INPUT_REQUIRED.value,
                "requires_approval": False,
            }

        return {
            "selected_operation_id": selected.id,
            "selected_operation_ids": operation_ids,
            "resolved_inputs": resolved_inputs,
        }
