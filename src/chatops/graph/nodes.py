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
from chatops.graph.planner_service import PlannerService
from chatops.graph.policy_service import PolicyService
from chatops.graph.precheck_service import PrecheckService
from chatops.graph.query_planner import QueryPlanningService
from chatops.graph.safe_node import safe_node
from chatops.graph.session_message_service import SessionMessageService
from chatops.graph.specialist_router import SpecialistRouter
from chatops.graph.state import GraphState
from chatops.graph.verifier_service import VerifierService
from chatops.graph.verifier_transition_service import VerifierTransitionService
from chatops.services.auth import format_missing_auth_headers, missing_auth_headers
from chatops.services.downstream_dispatcher import EntityResolutionError
from chatops.services.task_snapshot_builder import TaskSnapshotBuilder


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
        self.task_snapshot_builder = TaskSnapshotBuilder(
            command_message_builder=self.command_message_builder,
        )
        self.planner_service = PlannerService(
            llm_service=self.llm_service,
            registry_service=self.registry_service,
        )
        self.specialist_router = SpecialistRouter(registry_service=self.registry_service)
        self.verifier_service = VerifierService(llm_service=self.llm_service)
        self.verifier_transition_service = VerifierTransitionService()
        self.policy_service = PolicyService()
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
            "selected_specialist": None,
            "policy_decision": None,
            "verifier_route": None,
            "retry_count": 0,
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
    def plan_runtime(self, state: GraphState) -> GraphState:
        plan_object = self.planner_service.build(
            message_text=state.get("effective_message_text", state["message_text"]),
            request_type=state["request_type"],
        )
        if not isinstance(plan_object, dict):
            return {
                "plan_object": None,
                "selected_specialist": None,
                "current_step_index": 0,
                "total_steps": 0,
                "completed_steps": [],
            }
        candidate_steps = plan_object.get("candidate_steps") or []
        return {
            "plan_object": plan_object,
            "selected_specialist": str(plan_object.get("specialist") or ""),
            "current_step_index": 0,
            "total_steps": len(candidate_steps),
            "completed_steps": [],
        }

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
        selected_operation_id = prepared.get("selected_operation_id")
        operation = self.registry_service.get_entry(selected_operation_id) if selected_operation_id else None
        task_snapshot = self.task_snapshot_builder.build(
            operation=operation,
            request_status=str(prepared.get("request_status", state.get("request_status", ""))),
            request_type="query",
            resolved_inputs=prepared.get("resolved_inputs"),
            missing_inputs=prepared.get("missing_inputs"),
            risk_level=prepared.get("risk_level"),
            clarification_type=prepared.get("clarification_type"),
            is_ambiguous=bool(prepared.get("is_ambiguous", False)),
            summary=prepared.get("final_response"),
        )
        if task_snapshot is not None:
            prepared["task_snapshot"] = task_snapshot
        selected_operation_id = prepared.get("selected_operation_id")
        specialist = self.specialist_router.for_operation(selected_operation_id)
        specialist_result = specialist.describe(
            operation_id=selected_operation_id,
            resolved_inputs=prepared.get("resolved_inputs"),
            missing_inputs=prepared.get("missing_inputs"),
        )
        # 도메인별 입력 검증 경고 추가
        input_warnings = specialist.validate_inputs(
            operation_id=selected_operation_id,
            resolved_inputs=prepared.get("resolved_inputs"),
        )
        if input_warnings:
            specialist_result["input_warnings"] = input_warnings
        prepared["specialist_result"] = specialist_result
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
        # 도메인별 결과 포맷팅
        specialist = self.specialist_router.for_operation(operation_id)
        query_result = specialist.format_result(
            operation_id=operation_id,
            raw_result=query_result,
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
    def verify_query(self, state: GraphState) -> GraphState:
        retry_count = int(state.get("retry_count", 0))
        operation_id = state.get("selected_operation_id")
        verifier_decision = self.verifier_service.verify(
            request_type="query",
            operation_id=operation_id,
            execution_result=state.get("query_result"),
            message_text=state.get("effective_message_text", state.get("message_text")),
            resolved_inputs=state.get("resolved_inputs"),
        )
        policy_decision = self.policy_service.evaluate(
            operation_id=operation_id,
            risk_level=state.get("risk_level"),
            retry_count=retry_count,
            superseded=False,
        )
        verifier_route = self.verifier_transition_service.route(
            verifier_decision=verifier_decision,
            policy_decision=policy_decision,
        )
        if verifier_decision.get("decision") == "retry" and verifier_route == "escalate":
            verifier_decision = {
                **verifier_decision,
                "decision": "escalate",
                "follow_up_action": "human_review",
            }
        # specialist 재시도 전략 힌트 추가
        if verifier_route == "retry":
            specialist = self.specialist_router.for_operation(operation_id)
            retry_hint = specialist.suggest_retry_strategy(
                operation_id=operation_id,
                error_result=state.get("query_result") or {},
            )
            if retry_hint:
                verifier_decision = {**verifier_decision, "retry_hint": retry_hint}
        next_retry_count = retry_count + 1 if verifier_route == "retry" else retry_count
        return {
            "verifier_decision": verifier_decision,
            "policy_decision": policy_decision,
            "verifier_route": verifier_route,
            "retry_count": next_retry_count,
        }

    @safe_node
    def interpret_result(self, state: GraphState) -> GraphState:
        raw_result = state.get("query_result") or {}
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        interpreted_target = raw_result.get("result")
        if not isinstance(interpreted_target, dict):
            interpreted_target = raw_result
        final_response = self.llm_service.interpret_query_result(
            state["message_text"],
            interpreted_target,
        )
        return {
            "final_response": final_response,
            "request_status": RequestStatus.COMPLETED.value,
            "requires_approval": False,
            "task_snapshot": self.task_snapshot_builder.build(
                operation=operation,
                request_status=RequestStatus.COMPLETED.value,
                request_type="query",
                resolved_inputs=state.get("resolved_inputs"),
                missing_inputs=state.get("missing_inputs"),
                risk_level=state.get("risk_level"),
                clarification_type=state.get("clarification_type"),
                is_ambiguous=bool(state.get("is_ambiguous", False)),
                summary=final_response,
            ),
        }

    @safe_node
    def finalize_query_verifier_outcome(self, state: GraphState) -> GraphState:
        return self._build_verifier_terminal_state(state)

    @safe_node
    def plan_command(self, state: GraphState) -> GraphState:
        planned = self.command_planner.prepare(state)
        selected_operation_id = planned.get("selected_operation_id")
        operation = self.registry_service.get_entry(selected_operation_id) if selected_operation_id else None
        task_snapshot = self.task_snapshot_builder.build(
            operation=operation,
            request_status=str(planned.get("request_status", state.get("request_status", ""))),
            request_type="command",
            resolved_inputs=planned.get("resolved_inputs"),
            missing_inputs=planned.get("missing_inputs"),
            risk_level=planned.get("risk_level"),
            clarification_type=planned.get("clarification_type"),
            is_ambiguous=bool(planned.get("is_ambiguous", False)),
            summary=planned.get("final_response"),
        )
        if task_snapshot is not None:
            planned["task_snapshot"] = task_snapshot
        specialist = self.specialist_router.for_operation(selected_operation_id)
        specialist_result = specialist.describe(
            operation_id=selected_operation_id,
            resolved_inputs=planned.get("resolved_inputs"),
            missing_inputs=planned.get("missing_inputs"),
        )
        # 도메인별 입력 검증 경고 추가
        input_warnings = specialist.validate_inputs(
            operation_id=selected_operation_id,
            resolved_inputs=planned.get("resolved_inputs"),
        )
        if input_warnings:
            specialist_result["input_warnings"] = input_warnings
        planned["specialist_result"] = specialist_result
        policy_decision = self.policy_service.evaluate(
            operation_id=selected_operation_id,
            risk_level=planned.get("risk_level"),
            retry_count=int(state.get("retry_count", 0)),
            superseded=False,
        )
        planned["policy_decision"] = policy_decision
        planned["requires_approval"] = bool(
            planned.get("requires_approval", False) or policy_decision.get("requires_approval", False)
        )
        clarification_type = self.observability_service.derive_clarification_type(planned)
        if clarification_type is not None:
            planned["clarification_type"] = clarification_type
            if isinstance(planned.get("task_snapshot"), dict):
                planned["task_snapshot"]["clarification_type"] = clarification_type
            self.observability_service.log_clarification_event(
                request_id=state.get("request_id"),
                session_id=state.get("session_id"),
                user_id=state.get("user_id"),
                operation_id=planned.get("selected_operation_id"),
                clarification_type=clarification_type,
            )
        return planned

    def wait_for_approval(self, state: GraphState) -> GraphState:
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        # P0: TTL 만료 확인
        expires_at_str = state.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(timezone.utc) > expires_at:
                    final_response = "요청이 만료되었습니다. 다시 요청해주세요."
                    return {
                        "approval_granted": False,
                        "request_status": RequestStatus.APPROVAL_EXPIRED.value,
                        "requires_approval": False,
                        "final_response": final_response,
                        "error_code": "APPROVAL_EXPIRED",
                        "task_snapshot": self.task_snapshot_builder.build(
                            operation=operation,
                            request_status=RequestStatus.APPROVAL_EXPIRED.value,
                            request_type=state.get("request_type"),
                            resolved_inputs=state.get("resolved_inputs"),
                            missing_inputs=state.get("missing_inputs"),
                            risk_level=state.get("risk_level"),
                            clarification_type=state.get("clarification_type"),
                            is_ambiguous=bool(state.get("is_ambiguous", False)),
                            summary=final_response,
                        ),
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
                final_response = (
                    "입력한 확인값이 대상과 일치하지 않습니다. "
                    f"다음 값을 정확히 입력해야 합니다: {self._format_high_risk_confirmation_payload(expected_payload)}"
                )
                return {
                    "approval_granted": False,
                    "request_status": RequestStatus.REJECTED.value,
                    "requires_approval": False,
                    "final_response": final_response,
                    "task_snapshot": self.task_snapshot_builder.build(
                        operation=operation,
                        request_status=RequestStatus.REJECTED.value,
                        request_type=state.get("request_type"),
                        resolved_inputs=state.get("resolved_inputs"),
                        missing_inputs=state.get("missing_inputs"),
                        risk_level=state.get("risk_level"),
                        clarification_type=state.get("clarification_type"),
                        is_ambiguous=bool(state.get("is_ambiguous", False)),
                        summary=final_response,
                    ),
                }
            approved = True

        final_response = (
            state.get("final_response")
            if approved
            else "알겠습니다. 요청을 취소했습니다. 다른 작업이 필요하시면 말씀해주세요."
        )
        return {
            "approval_granted": bool(approved),
            "request_status": "approved" if approved else "rejected",
            "requires_approval": False,
            "final_response": final_response,
            "task_snapshot": self.task_snapshot_builder.build(
                operation=operation,
                request_status="approved" if approved else "rejected",
                request_type=state.get("request_type"),
                resolved_inputs=state.get("resolved_inputs"),
                missing_inputs=state.get("missing_inputs"),
                risk_level=state.get("risk_level"),
                clarification_type=state.get("clarification_type"),
                is_ambiguous=bool(state.get("is_ambiguous", False)),
                summary=final_response,
            ),
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
        # 도메인별 결과 포맷팅
        specialist = self.specialist_router.for_operation(operation_id)
        command_result = specialist.format_result(
            operation_id=operation_id,
            raw_result=command_result,
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
            "task_snapshot": self.task_snapshot_builder.build(
                operation=operation,
                request_status=RequestStatus.EXECUTING.value,
                request_type=state.get("request_type"),
                resolved_inputs=resolved_inputs,
                missing_inputs=state.get("missing_inputs"),
                risk_level=state.get("risk_level"),
                clarification_type=state.get("clarification_type"),
                is_ambiguous=bool(state.get("is_ambiguous", False)),
                summary=state.get("final_response"),
            ),
        }

    @safe_node
    def verify_command(self, state: GraphState) -> GraphState:
        retry_count = int(state.get("retry_count", 0))
        operation_id = state.get("selected_operation_id")
        verifier_decision = self.verifier_service.verify(
            request_type="command",
            operation_id=operation_id,
            execution_result=state.get("command_result"),
            message_text=state.get("effective_message_text", state.get("message_text")),
            resolved_inputs=state.get("resolved_inputs"),
        )
        policy_decision = self.policy_service.evaluate(
            operation_id=operation_id,
            risk_level=state.get("risk_level"),
            retry_count=retry_count,
            superseded=False,
        )
        verifier_route = self.verifier_transition_service.route(
            verifier_decision=verifier_decision,
            policy_decision=policy_decision,
        )
        if verifier_decision.get("decision") == "retry" and verifier_route == "escalate":
            verifier_decision = {
                **verifier_decision,
                "decision": "escalate",
                "follow_up_action": "human_review",
            }
        # specialist 재시도 전략 힌트 추가
        if verifier_route == "retry":
            specialist = self.specialist_router.for_operation(operation_id)
            retry_hint = specialist.suggest_retry_strategy(
                operation_id=operation_id,
                error_result=state.get("command_result") or {},
            )
            if retry_hint:
                verifier_decision = {**verifier_decision, "retry_hint": retry_hint}
        next_retry_count = retry_count + 1 if verifier_route == "retry" else retry_count
        return {
            "verifier_decision": verifier_decision,
            "policy_decision": policy_decision,
            "verifier_route": verifier_route,
            "retry_count": next_retry_count,
        }

    def respond_command(self, state: GraphState) -> GraphState:
        completed_steps = list(state.get("completed_steps") or [])
        operation_id = str(state.get("selected_operation_id") or "")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None

        if len(completed_steps) > 1:
            # 멀티스텝: 모든 단계 결과를 합산하여 응답
            lines = []
            for i, step in enumerate(completed_steps, start=1):
                step_op = step.get("operation_id", "")
                step_summary = (step.get("result") or {}).get("summary", "")
                lines.append(f"{i}. [{step_op}] {step_summary}")
            summary = "\n".join(lines)
            final_response = f"✅ {len(completed_steps)}개 작업을 모두 완료했습니다:\n{summary}"
        else:
            result = state.get("command_result") or {}
            summary = str(result.get("summary", "명령 실행 결과가 없습니다."))
            final_response = self.command_message_builder.build_command_success_message(operation_id, summary)

        return {
            "final_response": final_response,
            "request_status": RequestStatus.COMPLETED.value,
            "requires_approval": False,
            "task_snapshot": self.task_snapshot_builder.build(
                operation=operation,
                request_status=RequestStatus.COMPLETED.value,
                request_type=state.get("request_type"),
                resolved_inputs=state.get("resolved_inputs"),
                missing_inputs=state.get("missing_inputs"),
                risk_level=state.get("risk_level"),
                clarification_type=state.get("clarification_type"),
                is_ambiguous=bool(state.get("is_ambiguous", False)),
                summary=final_response,
            ),
        }

    @safe_node
    def advance_step(self, state: GraphState) -> GraphState:
        """멀티스텝 플랜에서 현재 단계 결과를 저장하고 다음 단계를 준비한다.

        - completed_steps에 현재 단계 결과를 append
        - current_step_index를 증가
        - 다음 단계가 있으면 selected_operation_id를 교체하고 결과 필드를 초기화
        - 다음 단계가 없으면 상태만 갱신 (이후 노드에서 최종 응답 생성)
        """
        plan_object = state.get("plan_object") or {}
        candidate_steps = list(plan_object.get("candidate_steps") or [])
        current_index = int(state.get("current_step_index", 0))
        request_type = state.get("request_type", "command")

        # 현재 단계 결과 수집
        step_result = (
            state.get("command_result") if request_type == "command" else state.get("query_result")
        ) or {}
        current_step = candidate_steps[current_index] if current_index < len(candidate_steps) else {}
        completed_steps = list(state.get("completed_steps") or [])
        completed_steps.append({
            "step_index": current_index,
            "operation_id": current_step.get("operation_id"),
            "title": current_step.get("title", ""),
            "result": step_result,
        })

        next_index = current_index + 1

        if next_index < len(candidate_steps):
            # 다음 단계 준비
            next_step = candidate_steps[next_index]
            next_operation_id = str(next_step.get("operation_id") or "")
            return {
                "current_step_index": next_index,
                "completed_steps": completed_steps,
                "selected_operation_id": next_operation_id,
                "resolved_inputs": None,   # 다음 단계는 입력을 새로 해결
                "command_result": None,
                "query_result": None,
                "verifier_route": None,
                "retry_count": 0,
            }

        # 모든 단계 완료
        return {
            "current_step_index": next_index,
            "completed_steps": completed_steps,
        }

    @safe_node
    def finalize_command_verifier_outcome(self, state: GraphState) -> GraphState:
        return self._build_verifier_terminal_state(state)

    def _build_verifier_terminal_state(self, state: GraphState) -> GraphState:
        operation_id = str(state.get("selected_operation_id") or "")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        verifier_decision = state.get("verifier_decision") or {}
        verifier_route = str(state.get("verifier_route") or "stop")
        request_status = self._verifier_terminal_status(verifier_route)
        missing_inputs = self._verifier_missing_inputs(state)
        clarification_type = state.get("clarification_type")
        if request_status == RequestStatus.INPUT_REQUIRED.value:
            clarification_type = "missing_input"

        summary = str(verifier_decision.get("summary") or self._verifier_default_summary(verifier_route))
        if state.get("request_type") == "command" and verifier_route == "stop":
            final_response = self.command_message_builder.build_command_failure_message(operation_id, summary)
        else:
            final_response = summary

        task_snapshot = self.task_snapshot_builder.build(
            operation=operation,
            request_status=request_status,
            request_type=state.get("request_type"),
            resolved_inputs=state.get("resolved_inputs"),
            missing_inputs=missing_inputs,
            risk_level=state.get("risk_level"),
            clarification_type=clarification_type,
            is_ambiguous=bool(state.get("is_ambiguous", False)),
            summary=final_response,
        )
        return {
            "final_response": final_response,
            "request_status": request_status,
            "requires_approval": False,
            "missing_inputs": missing_inputs,
            "clarification_type": clarification_type,
            "task_snapshot": task_snapshot,
        }

    @staticmethod
    def _verifier_terminal_status(verifier_route: str) -> str:
        if verifier_route == "clarify":
            return RequestStatus.INPUT_REQUIRED.value
        if verifier_route == "escalate":
            return RequestStatus.ESCALATED.value
        return RequestStatus.FAILED.value

    @staticmethod
    def _verifier_default_summary(verifier_route: str) -> str:
        if verifier_route == "clarify":
            return "추가 입력이 필요합니다."
        if verifier_route == "escalate":
            return "사람의 확인이 필요합니다."
        return "요청을 종료합니다."

    @staticmethod
    def _verifier_missing_inputs(state: GraphState) -> list[str]:
        verifier_decision = state.get("verifier_decision")
        if isinstance(verifier_decision, dict):
            missing_inputs = verifier_decision.get("missing_inputs")
            if isinstance(missing_inputs, list):
                return [str(item) for item in missing_inputs]
        existing = state.get("missing_inputs") or []
        return [str(item) for item in existing]

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
            user_role=state.get("user_role"),
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
