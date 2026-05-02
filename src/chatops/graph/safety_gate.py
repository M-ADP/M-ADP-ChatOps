"""Agent Loop용 안전 게이트.

tool_call이 실행되기 전에 auth, precheck, approval을 검사한다.
Blocked 결과는 하드 실패가 아니라 tool_result error로 LLM에게 전달되어,
LLM이 사용자에게 설명하거나 다른 행동을 선택할 수 있게 한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from chatops.graph.approval_policy import ApprovalPolicyService
from chatops.graph.precheck_service import PrecheckService
from chatops.graph.specialist_router import SpecialistRouter
from chatops.services.auth import missing_auth_headers, format_missing_auth_headers
from chatops.services.registry import RegistryEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyDecision:
    """safety_gate 평가 결과."""
    action: Literal["execute", "blocked", "needs_approval"]
    resolved_inputs: dict[str, Any] | None = None
    resolved_ids: dict[str, Any] | None = None
    error_message: str | None = None
    interrupt_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class SafetyGateService:
    """Agent Loop의 안전 게이트. auth → validate → precheck → approval 순서로 검사한다."""
    precheck_service: PrecheckService
    specialist_router: SpecialistRouter = field(default_factory=SpecialistRouter)
    approval_policy: ApprovalPolicyService = field(default_factory=ApprovalPolicyService)

    def evaluate(
        self,
        *,
        operation: RegistryEntry,
        resolved_inputs: dict[str, Any],
        user_id: str,
        user_role: str | None,
        request_id: int | None = None,
        session_id: int | None = None,
    ) -> SafetyDecision:
        """tool_call에 대한 안전성을 평가한다.

        Returns:
            SafetyDecision:
                - execute: 즉시 실행 가능
                - blocked: 에러 발생 (auth 실패, precheck 실패 등)
                - needs_approval: 사용자 승인 필요 (interrupt 필요)
        """
        # 1. Auth 체크
        missing_headers = missing_auth_headers(
            operation.required_headers,
            user_id=user_id,
            user_role=user_role,
        )
        if missing_headers:
            return SafetyDecision(
                action="blocked",
                error_message=format_missing_auth_headers(missing_headers),
            )

        # 2. Specialist 입력 유효성 검사
        specialist = self.specialist_router.for_operation(operation.id)
        warnings = specialist.validate_inputs(
            operation_id=operation.id,
            resolved_inputs=resolved_inputs,
        )
        if warnings:
            return SafetyDecision(
                action="blocked",
                error_message="\n".join(warnings),
            )

        # 3. Precheck (엔티티 존재 확인 + ID resolution)
        precheck_result = self.precheck_service.run(
            operation=operation,
            resolved_inputs=resolved_inputs,
            user_id=user_id,
            user_role=user_role,
        )
        # 동명이인: LLM 피드백 루프를 거치지 않고 상태 머신이 직접 interrupt한다.
        if precheck_result.get("disambiguation_required"):
            partial_ids = precheck_result.get("resolved_ids") or {}
            nickname_query = resolved_inputs.get("references", {}).get("target_nickname", "")
            return SafetyDecision(
                action="needs_approval",
                resolved_inputs=resolved_inputs,
                resolved_ids=partial_ids,
                interrupt_payload={
                    "type": "disambiguation",
                    "request_id": request_id,
                    "session_id": session_id,
                    "query": nickname_query,
                    "candidates": precheck_result.get("candidates", []),
                },
            )
        if precheck_result.get("error"):
            return SafetyDecision(
                action="blocked",
                error_message=str(precheck_result["error"]),
            )

        resolved_ids = precheck_result.get("resolved_ids") or {}

        # 4. Approval 체크
        if operation.requires_confirmation:
            plan_text = self._build_plan_text(operation, resolved_inputs)
            return SafetyDecision(
                action="needs_approval",
                resolved_inputs=resolved_inputs,
                resolved_ids=resolved_ids,
                interrupt_payload={
                    "request_id": request_id,
                    "session_id": session_id,
                    "operation_id": operation.id,
                    "plan": plan_text,
                    "risk_level": operation.risk_level,
                },
            )

        # 모든 검사 통과 — 즉시 실행
        return SafetyDecision(
            action="execute",
            resolved_inputs=resolved_inputs,
            resolved_ids=resolved_ids,
        )

    def _build_plan_text(
        self,
        operation: RegistryEntry,
        resolved_inputs: dict[str, Any],
    ) -> str:
        """승인 요청 시 사용자에게 보여줄 실행 계획 텍스트."""
        references = resolved_inputs.get("references", {})
        body = resolved_inputs.get("body", {})

        parts: list[str] = [f"작업: {operation.capability or operation.id}"]

        if references.get("project_name"):
            parts.append(f"프로젝트: {references['project_name']}")
        if references.get("application_name"):
            parts.append(f"앱: {references['application_name']}")
        if references.get("target_nickname"):
            parts.append(f"대상 사용자: {references['target_nickname']}")

        if body:
            for key, value in body.items():
                if key not in ("project_id",):
                    parts.append(f"{key}: {value}")

        if operation.risk_level == "high":
            parts.append("⚠️ 이 작업은 되돌릴 수 없습니다.")

        return "\n".join(parts)
