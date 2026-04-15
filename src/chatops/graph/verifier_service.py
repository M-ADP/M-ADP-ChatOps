from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chatops.services.decision_trace import log_decision_trace

# operation별 응답에 반드시 있어야 할 최소 필드
_EXPECTED_FIELDS: dict[str, list[str]] = {
    "project.get": ["id", "name"],
    "project.list_projects": ["items"],
    "project.list_members": ["items"],
    "application.get_apps": ["items"],
    "application.get_apps_status": ["status"],
    "application.get_apps_logs": ["logs"],
    "application.get_apps_details": ["id"],
    "monitoring.get_app_deployment_traffic": ["traffic"],
}


@dataclass(frozen=True)
class VerifierService:
    llm_service: Any | None = None

    def verify(
        self,
        *,
        request_type: str,
        operation_id: str | None,
        execution_result: dict[str, Any] | None,
        message_text: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        del request_type
        result = execution_result or {}
        trace_data = {
            "operation_id": operation_id,
            "status_code": int(result.get("status_code", 200)),
            "success": result.get("success"),
            "summary": result.get("summary"),
        }

        # 1. LLM verifier (컨텍스트 포함)
        if hasattr(self.llm_service, "verify_execution"):
            decision = self.llm_service.verify_execution(
                execution_result=result,
                operation_id=operation_id,
                message_text=message_text,
            )
            if isinstance(decision, dict):
                log_decision_trace(
                    stage="verifier",
                    decision=str(decision.get("decision") or "unknown"),
                    reason="llm verifier decision",
                    data={**trace_data, "follow_up_action": decision.get("follow_up_action")},
                )
                return decision

        # 2. 의미론적 검증 (success=True여도 데이터 품질 확인)
        if result.get("success") is not False:
            semantic = self._check_semantic_quality(
                result=result,
                operation_id=operation_id,
            )
            if semantic is not None:
                log_decision_trace(
                    stage="verifier",
                    decision=str(semantic.get("decision") or "unknown"),
                    reason="semantic quality verifier decision",
                    data={**trace_data, "follow_up_action": semantic.get("follow_up_action")},
                )
                return semantic

        # 3. status_code 기반 검증 (기존 로직)
        decision = self._status_code_based_verify(result)
        log_decision_trace(
            stage="verifier",
            decision=str(decision.get("decision") or "unknown"),
            reason="status code based verifier decision",
            data={**trace_data, "follow_up_action": decision.get("follow_up_action")},
        )
        return decision

    # ──────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────

    def _check_semantic_quality(
        self,
        *,
        result: dict[str, Any],
        operation_id: str | None,
    ) -> dict[str, object] | None:
        """success=True여도 의미적으로 문제가 있는 경우를 감지한다."""
        data = result.get("data") or result.get("result")

        # 빈 리스트 결과
        if isinstance(data, list) and len(data) == 0:
            return {
                "decision": "success",
                "summary": result.get("summary") or "조회 결과가 없습니다.",
                "missing_inputs": [],
                "follow_up_action": "complete",
                "semantic_warning": "empty_result",
            }

        # 빈 딕셔너리 결과
        if isinstance(data, dict) and not data:
            return {
                "decision": "success",
                "summary": result.get("summary") or "조회 결과가 비어 있습니다.",
                "missing_inputs": [],
                "follow_up_action": "complete",
                "semantic_warning": "empty_result",
            }

        # operation별 예상 필드 누락 확인
        if operation_id and isinstance(data, dict):
            expected = _EXPECTED_FIELDS.get(operation_id, [])
            if expected:
                missing = [f for f in expected if f not in data]
                # 절반 이상 누락이면 clarify
                if len(missing) >= max(1, len(expected) // 2):
                    return {
                        "decision": "clarify",
                        "summary": f"응답에 예상 필드가 누락됐습니다: {', '.join(missing)}",
                        "missing_inputs": [],
                        "follow_up_action": "clarify",
                        "semantic_warning": "missing_expected_fields",
                    }

        return None

    def _status_code_based_verify(self, result: dict[str, Any]) -> dict[str, object]:
        """status_code 기반 기존 검증 로직."""
        status_code = int(result.get("status_code", 200))
        if result.get("success") is False:
            if status_code >= 500:
                return {
                    "decision": "retry",
                    "summary": str(result.get("summary", "일시적 오류가 발생했습니다.")),
                    "missing_inputs": [],
                    "follow_up_action": "retry",
                }
            if status_code in {400, 404, 409, 422}:
                return {
                    "decision": "clarify",
                    "summary": str(result.get("summary", "추가 입력이 필요합니다.")),
                    "missing_inputs": [],
                    "follow_up_action": "fill_inputs",
                }
            if status_code in {401, 403}:
                return {
                    "decision": "escalate",
                    "summary": str(result.get("summary", "권한 확인이 필요합니다.")),
                    "missing_inputs": [],
                    "follow_up_action": "human_review",
                }
            return {
                "decision": "stop",
                "summary": str(result.get("summary", "요청을 종료합니다.")),
                "missing_inputs": [],
                "follow_up_action": "stop",
            }
        return {
            "decision": "success",
            "summary": str(result.get("summary", "실행 결과를 확인했습니다.")),
            "missing_inputs": [],
            "follow_up_action": "complete",
        }
