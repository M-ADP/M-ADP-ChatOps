from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerifierService:
    llm_service: Any | None = None

    def verify(
        self,
        *,
        request_type: str,
        operation_id: str | None,
        execution_result: dict[str, Any] | None,
    ) -> dict[str, object]:
        del request_type, operation_id
        result = execution_result or {}
        if hasattr(self.llm_service, "verify_execution"):
            decision = self.llm_service.verify_execution(execution_result=result)
            if isinstance(decision, dict):
                return decision
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
