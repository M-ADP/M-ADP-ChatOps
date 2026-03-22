from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from chatops.graph.state import GraphState


class WorkflowNodes:
    def __init__(self, llm_service: Any, registry_service: Any, adapter_service: Any, resolver_service: Any) -> None:
        self.llm_service = llm_service
        self.registry_service = registry_service
        self.adapter_service = adapter_service
        self.resolver_service = resolver_service

    def ingest_request(self, state: GraphState) -> GraphState:
        return {
            "request_status": "processing",
            "requires_approval": False,
            "selected_operation_ids": [],
        }

    def classify_request(self, state: GraphState) -> GraphState:
        classification = self.llm_service.classify(state["message_text"])
        return {
            "request_type": str(classification["request_type"]),
            "intent": str(classification.get("intent", "")),
            "classification_reason": str(classification.get("classification_reason", "")),
            "classification_confidence": float(classification.get("classification_confidence", 0.0)),
        }

    def route_request(self, state: GraphState) -> GraphState:
        return {"route": state["request_type"]}

    def answer_inquiry(self, state: GraphState) -> GraphState:
        return {
            "final_response": self.llm_service.answer_inquiry(state["message_text"]),
            "request_status": "completed",
            "requires_approval": False,
        }

    def prepare_query(self, state: GraphState) -> GraphState:
        candidates = self.registry_service.find_candidates(state["message_text"], usable_in="query")
        selected = candidates[0] if candidates else None
        return {
            "selected_operation_id": selected.id if selected is not None else None,
            "selected_operation_ids": [candidate.id for candidate in candidates],
        }

    def execute_query(self, state: GraphState) -> GraphState:
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        if operation is None:
            return {
                "query_result": {"summary": "적절한 조회 API를 찾지 못했습니다."},
            }

        resolved_inputs = self.resolver_service.resolve(operation, state["message_text"])
        return {
            "resolved_inputs": resolved_inputs,
            "query_result": self.adapter_service.execute_query(
                operation,
                state["user_id"],
                user_role=state.get("user_role"),
                org_id=state.get("org_id"),
                resolved_inputs=resolved_inputs,
            ),
        }

    def interpret_result(self, state: GraphState) -> GraphState:
        raw_result = state.get("query_result") or {}
        return {
            "final_response": self.llm_service.interpret_query_result(
                state["message_text"],
                raw_result,
            ),
            "request_status": "completed",
            "requires_approval": False,
        }

    def plan_command(self, state: GraphState) -> GraphState:
        candidates = self.registry_service.find_candidates(state["message_text"], usable_in="command")
        operation_ids = [candidate.id for candidate in candidates]
        selected = candidates[0] if candidates else None
        return {
            "selected_operation_id": selected.id if selected is not None else None,
            "selected_operation_ids": operation_ids,
            "final_response": self.llm_service.plan_command(state["message_text"], operation_ids),
            "request_status": "pending_approval",
            "requires_approval": True,
        }

    def wait_for_approval(self, state: GraphState) -> GraphState:
        approved = interrupt(
            {
                "request_id": state["request_id"],
                "session_id": state["session_id"],
                "plan": state.get("final_response"),
                "selected_operation_ids": list(state.get("selected_operation_ids", [])),
            }
        )
        return {
            "approval_granted": bool(approved),
            "request_status": "approved" if approved else "rejected",
            "requires_approval": False,
            "final_response": state.get("final_response") if approved else "명령 실행이 거절되었습니다.",
        }

    def execute_command(self, state: GraphState) -> GraphState:
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        if operation is None:
            return {
                "command_result": {"success": False, "summary": "적절한 명령 API를 찾지 못했습니다."},
                "request_status": "failed",
                "requires_approval": False,
            }

        resolved_inputs = self.resolver_service.resolve(operation, state["message_text"])
        return {
            "resolved_inputs": resolved_inputs,
            "command_result": self.adapter_service.execute_command(
                operation,
                state["user_id"],
                user_role=state.get("user_role"),
                org_id=state.get("org_id"),
                resolved_inputs=resolved_inputs,
            ),
            "request_status": "executing",
            "requires_approval": False,
        }

    def respond_command(self, state: GraphState) -> GraphState:
        result = state.get("command_result") or {}
        summary = str(result.get("summary", "명령 실행 결과가 없습니다."))
        if result.get("success") is False:
            return {
                "final_response": f"명령 실행 실패: {summary}",
                "request_status": "failed",
                "requires_approval": False,
            }
        return {
            "final_response": f"명령 실행 응답: {summary}",
            "request_status": "completed",
            "requires_approval": False,
        }
