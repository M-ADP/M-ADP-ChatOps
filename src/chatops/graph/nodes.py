from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from langgraph.types import interrupt

from chatops.domain.enums import RequestStatus
from chatops.graph.approval_policy import ApprovalPolicyService
from chatops.graph.command_message_builder import CommandMessageBuilder
from chatops.graph.command_planner import CommandPlanningService
from chatops.graph.input_requirement_service import InputRequirementService
from chatops.graph.interaction_prompt_service import InteractionPromptService
from chatops.graph.observability_service import AuditObservabilityService
from chatops.graph.precheck_service import PrecheckService
from chatops.graph.query_planner import QueryPlanningService
from chatops.graph.safe_node import safe_node
from chatops.graph.session_message_service import SessionMessageService
from chatops.graph.state import GraphState
from chatops.services.auth import format_missing_auth_headers, missing_auth_headers
from chatops.services.downstream_dispatcher import EntityResolutionError


class WorkflowNodes:
    def __init__(
        self,
        llm_service: Any,
        registry_service: Any,
        downstream_dispatcher: Any,
        resolver_service: Any,
        approval_ttl_seconds: int = 900,
    ) -> None:
        self.llm_service = llm_service
        self.registry_service = registry_service
        self.downstream_dispatcher = downstream_dispatcher
        self.resolver_service = resolver_service
        self.approval_ttl_seconds = approval_ttl_seconds
        self.approval_policy = ApprovalPolicyService()
        self.command_message_builder = CommandMessageBuilder()
        self.input_requirement_service = InputRequirementService()
        self.session_message_service = SessionMessageService()
        self.interaction_prompt_service = InteractionPromptService(
            command_message_builder=self.command_message_builder,
        )
        self.precheck_service = PrecheckService(
            downstream_dispatcher=self.downstream_dispatcher,
        )
        self.observability_service = AuditObservabilityService()
        self.query_planner = QueryPlanningService(
            registry_service=self.registry_service,
            resolver_service=self.resolver_service,
            auth_precheck_failure=self._auth_precheck_failure,
            missing_required_inputs=self.input_requirement_service.missing_required_inputs,
            ambiguity_question_builder=self.interaction_prompt_service.build_query_ambiguity_question,
            missing_input_response_builder=self.command_message_builder.format_query_missing_input_response,
        )
        self.command_planner = CommandPlanningService(
            registry_service=self.registry_service,
            resolver_service=self.resolver_service,
            auth_precheck_failure=self._auth_precheck_failure,
            missing_required_inputs=self.input_requirement_service.missing_required_inputs,
            ambiguity_response_builder=self.interaction_prompt_service.build_command_ambiguity_response,
            missing_input_response_builder=self.command_message_builder.format_missing_input_response,
            precheck_service=self.precheck_service,
            risk_aware_plan_builder=self._build_risk_aware_plan,
        )

    def ingest_request(self, state: GraphState) -> GraphState:
        effective_message_text = self.session_message_service.effective_message_text(state)
        now = datetime.now(timezone.utc).isoformat()
        return {
            "request_status": "processing",
            "requires_approval": False,
            "selected_operation_ids": [],
            "effective_message_text": effective_message_text,
            "is_ambiguous": False,
            "ambiguity_candidates": [],
            "clarification_question": None,
            "precheck_passed": False,
            "resolved_ids": None,
            "precheck_error": None,
            "error_code": None,
            "clarification_type": None,
            "fallback_used": False,
            "execution_audit": None,
            "created_at": now,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=self.approval_ttl_seconds)
            ).isoformat(),
        }

    @safe_node
    def classify_request(self, state: GraphState) -> GraphState:
        classification = self.llm_service.classify(state.get("effective_message_text", state["message_text"]))
        return {
            "request_type": str(classification["request_type"]),
            "intent": str(classification.get("intent", "")),
            "classification_reason": str(classification.get("classification_reason", "")),
            "classification_confidence": float(classification.get("classification_confidence", 0.0)),
        }

    def route_request(self, state: GraphState) -> GraphState:
        return {"route": state["request_type"]}

    @safe_node
    def answer_inquiry(self, state: GraphState) -> GraphState:
        supported_operations = self.interaction_prompt_service.build_inquiry_operation_context(
            state["message_text"],
            registry_service=self.registry_service,
        )
        return {
            "final_response": self.llm_service.answer_inquiry(
                state["message_text"],
                supported_operations=supported_operations,
            ),
            "request_status": "completed",
            "requires_approval": False,
        }

    @safe_node
    def prepare_query(self, state: GraphState) -> GraphState:
        prepared = self.query_planner.prepare(state)
        clarification_type = self.observability_service.derive_clarification_type(prepared)
        if clarification_type is not None:
            prepared["clarification_type"] = clarification_type
            self.observability_service.log_clarification_event(
                request_id=state.get("request_id"),
                session_id=state.get("session_id"),
                user_id=state.get("user_id"),
                operation_id=prepared.get("selected_operation_id"),
                clarification_type=clarification_type,
            )
        return prepared

    @safe_node
    def execute_query(self, state: GraphState) -> GraphState:
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        if operation is None:
            return {
                "query_result": {"summary": "적절한 조회 API를 찾지 못했습니다."},
            }

        resolved_inputs = state.get("resolved_inputs") or self.resolver_service.resolve(
            operation,
            state.get("effective_message_text", state["message_text"]),
            session_context=state.get("session_context"),
        )
        started_at = perf_counter()
        query_result = self._run_awaitable(
            self.downstream_dispatcher.execute_query(
                operation,
                state["user_id"],
                user_role=state.get("user_role"),
                org_id=state.get("org_id"),
                resolved_inputs=resolved_inputs,
            )
        )
        audit_payload = self.observability_service.log_downstream_execution(
            request_id=state.get("request_id"),
            session_id=state.get("session_id"),
            user_id=state.get("user_id"),
            operation_id=operation.id,
            result=query_result,
            started_at=started_at,
            clarification_type=state.get("clarification_type"),
        )
        return {
            "resolved_inputs": resolved_inputs,
            "query_result": query_result,
            "fallback_used": bool(query_result.get("fallback_used", False)),
            "execution_audit": audit_payload,
        }

    @safe_node
    def interpret_result(self, state: GraphState) -> GraphState:
        raw_result = state.get("query_result") or {}
        status_code = int(raw_result.get("status_code", 200))
        if raw_result.get("success") is False or status_code >= 400:
            return {
                "final_response": str(raw_result.get("summary", "조회 요청을 처리하지 못했습니다.")),
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
            }
        interpreted_target = raw_result.get("result")
        if not isinstance(interpreted_target, dict):
            interpreted_target = raw_result
        return {
            "final_response": self.llm_service.interpret_query_result(
                state["message_text"],
                interpreted_target,
            ),
            "request_status": RequestStatus.COMPLETED.value,
            "requires_approval": False,
        }

    @safe_node
    def plan_command(self, state: GraphState) -> GraphState:
        planned = self.command_planner.prepare(state)
        clarification_type = self.observability_service.derive_clarification_type(planned)
        if clarification_type is not None:
            planned["clarification_type"] = clarification_type
            self.observability_service.log_clarification_event(
                request_id=state.get("request_id"),
                session_id=state.get("session_id"),
                user_id=state.get("user_id"),
                operation_id=planned.get("selected_operation_id"),
                clarification_type=clarification_type,
            )
        return planned

    def wait_for_approval(self, state: GraphState) -> GraphState:
        # P0: TTL 만료 확인
        expires_at_str = state.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(timezone.utc) > expires_at:
                    return {
                        "approval_granted": False,
                        "request_status": RequestStatus.APPROVAL_EXPIRED.value,
                        "requires_approval": False,
                        "final_response": "요청이 만료되었습니다. 다시 요청해주세요.",
                        "error_code": "APPROVAL_EXPIRED",
                    }
            except (ValueError, TypeError):
                pass

        approved = interrupt(
            {
                "request_id": state["request_id"],
                "session_id": state["session_id"],
                "plan": state.get("final_response"),
                "selected_operation_ids": list(state.get("selected_operation_ids", [])),
                "risk_level": state.get("risk_level"),
            }
        )

        # P1: high risk에서 exact-name confirmation 처리
        risk_level = state.get("risk_level", "medium")
        if risk_level == "high" and isinstance(approved, str):
            expected_payload = self._build_high_risk_confirmation_payload(
                state.get("selected_operation_id") or "",
                state.get("resolved_inputs") or {},
            )
            if expected_payload and not self._matches_high_risk_confirmation(approved, expected_payload):
                return {
                    "approval_granted": False,
                    "request_status": RequestStatus.REJECTED.value,
                    "requires_approval": False,
                    "final_response": (
                        "입력한 확인값이 대상과 일치하지 않습니다. "
                        f"다음 값을 정확히 입력해야 합니다: {self._format_high_risk_confirmation_payload(expected_payload)}"
                    ),
                }
            approved = True

        return {
            "approval_granted": bool(approved),
            "request_status": "approved" if approved else "rejected",
            "requires_approval": False,
            "final_response": state.get("final_response") if approved else "알겠습니다. 요청을 취소했습니다. 다른 작업이 필요하시면 말씀해주세요.",
        }

    @safe_node
    def execute_command(self, state: GraphState) -> GraphState:
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        if operation is None:
            return {
                "command_result": {"success": False, "summary": "적절한 명령 API를 찾지 못했습니다."},
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
            }

        resolved_inputs = state.get("resolved_inputs") or self.resolver_service.resolve(
            operation,
            state.get("effective_message_text", state["message_text"]),
            session_context=state.get("session_context"),
        )

        started_at = perf_counter()
        command_result = self._run_awaitable(
            self.downstream_dispatcher.execute_command(
                operation,
                state["user_id"],
                user_role=state.get("user_role"),
                org_id=state.get("org_id"),
                resolved_inputs=resolved_inputs,
            )
        )
        audit_payload = self.observability_service.log_downstream_execution(
            request_id=state.get("request_id"),
            session_id=state.get("session_id"),
            user_id=state.get("user_id"),
            operation_id=operation.id,
            result=command_result,
            started_at=started_at,
            clarification_type=state.get("clarification_type"),
        )
        return {
            "resolved_inputs": resolved_inputs,
            "command_result": command_result,
            "request_status": RequestStatus.EXECUTING.value,
            "requires_approval": False,
            "fallback_used": bool(command_result.get("fallback_used", False)),
            "execution_audit": audit_payload,
        }

    def respond_command(self, state: GraphState) -> GraphState:
        result = state.get("command_result") or {}
        summary = str(result.get("summary", "명령 실행 결과가 없습니다."))
        operation_id = str(state.get("selected_operation_id") or "")
        if result.get("success") is False:
            return {
                "final_response": self.command_message_builder.build_command_failure_message(operation_id, summary),
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
            }
        return {
            "final_response": self.command_message_builder.build_command_success_message(operation_id, summary),
            "request_status": RequestStatus.COMPLETED.value,
            "requires_approval": False,
        }

    # ──────────────────────────────────────────────────
    # P1: Pre-check — 대상 엔티티 존재 여부 사전 확인
    # ──────────────────────────────────────────────────

    def _run_precheck(
        self,
        operation,
        resolved_inputs: dict[str, Any],
        user_id: str,
        user_role: str | None,
    ) -> dict[str, Any]:
        return self.precheck_service.run(
            operation=operation,
            resolved_inputs=resolved_inputs,
            user_id=user_id,
            user_role=user_role,
        )

    async def _precheck_project(
        self, user_id: str, user_role: str | None, project_name: str,
    ) -> dict[str, Any]:
        return await self.precheck_service._precheck_project(
            user_id=user_id,
            user_role=user_role,
            project_name=project_name,
        )

    async def _precheck_application(
        self, user_id: str, user_role: str | None, project_id: int, app_name: str,
    ) -> dict[str, Any]:
        return await self.precheck_service._precheck_application(
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
            app_name=app_name,
        )

    async def _precheck_user(self, nickname: str) -> dict[str, Any]:
        return await self.precheck_service._precheck_user(nickname)

    @staticmethod
    def _find_similar_names(target: str, names: list[str], limit: int = 3) -> list[str]:
        return PrecheckService._find_similar_names(target, names, limit)

    @staticmethod
    def _operation_needs_project(operation_id: str) -> bool:
        return PrecheckService._operation_needs_project(operation_id)

    @staticmethod
    def _operation_needs_application(operation_id: str) -> bool:
        return PrecheckService._operation_needs_application(operation_id)

    @staticmethod
    def _operation_needs_target_user(operation_id: str) -> bool:
        return PrecheckService._operation_needs_target_user(operation_id)

    # ──────────────────────────────────────────────────
    # P1: Risk-level 별 승인 메시지 빌더
    # ──────────────────────────────────────────────────

    def _build_risk_aware_plan(self, operation, resolved_inputs: dict[str, Any]) -> str:
        """risk_level에 따라 차등화된 승인 메시지를 생성한다."""
        risk_level = operation.risk_level

        if risk_level == "high":
            return self._build_high_risk_plan(operation, resolved_inputs)
        # medium (default) — 기존 plan 메시지
        return self.command_message_builder.build_command_plan(operation, resolved_inputs)

    def _build_high_risk_plan(self, operation, resolved_inputs: dict[str, Any]) -> str:
        plan_detail = self.command_message_builder.build_command_plan(operation, resolved_inputs)
        return self.approval_policy.build_high_risk_plan(
            operation_id=operation.id,
            plan_detail=plan_detail,
            resolved_inputs=resolved_inputs,
        )

    def _extract_target_name(self, state: GraphState) -> str | None:
        """state에서 high-risk 확인을 위한 대상 이름을 추출한다."""
        resolved_inputs = state.get("resolved_inputs") or {}
        operation_id = state.get("selected_operation_id") or ""
        return self._extract_target_name_from_inputs(operation_id, resolved_inputs)

    def _extract_target_name_from_inputs(
        self, operation_id: str, resolved_inputs: dict[str, Any],
    ) -> str | None:
        return self.approval_policy.extract_target_name(
            operation_id=operation_id,
            resolved_inputs=resolved_inputs,
        )

    def _build_high_risk_confirmation_payload(
        self,
        operation_id: str,
        resolved_inputs: dict[str, Any],
    ) -> dict[str, str]:
        return self.approval_policy.build_confirmation_payload(
            operation_id=operation_id,
            resolved_inputs=resolved_inputs,
        )

    @staticmethod
    def _format_high_risk_confirmation_payload(payload: dict[str, str]) -> str:
        return ApprovalPolicyService().format_confirmation_payload(payload)

    def _matches_high_risk_confirmation(
        self,
        approved: str,
        expected_payload: dict[str, str],
    ) -> bool:
        return self.approval_policy.matches_confirmation(approved, expected_payload)

    def _auth_precheck_failure(
        self,
        operation,
        state: GraphState,
        selected_operation_ids: list[str],
    ) -> GraphState | None:
        missing_headers = missing_auth_headers(
            operation.required_headers,
            user_id=state.get("user_id"),
            request_id=None,
            user_role=state.get("user_role"),
            org_id=state.get("org_id"),
        )
        if not missing_headers:
            return None
        return {
            "selected_operation_id": operation.id,
            "selected_operation_ids": selected_operation_ids,
            "final_response": format_missing_auth_headers(missing_headers),
            "request_status": RequestStatus.FAILED.value,
            "requires_approval": False,
            "error_code": "AUTH_CONTEXT_MISSING",
        }

    def _run_awaitable(self, awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("async downstream 호출은 현재 sync workflow에서만 지원합니다.")
