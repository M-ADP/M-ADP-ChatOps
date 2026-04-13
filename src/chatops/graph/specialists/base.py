from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BaseSpecialist:
    name: str

    def describe(
        self,
        *,
        operation_id: str | None,
        resolved_inputs: dict[str, object] | None,
        missing_inputs: list[str] | None,
    ) -> dict[str, object]:
        return {
            "specialist": self.name,
            "operation_id": operation_id,
            "summary": f"{self.name} specialist를 선택했습니다.",
            "resolved_inputs": resolved_inputs or {},
            "missing_inputs": list(missing_inputs or []),
        }

    def validate_inputs(
        self,
        *,
        operation_id: str | None,
        resolved_inputs: dict[str, object] | None,
    ) -> list[str]:
        """도메인별 입력 유효성 검사. 문제가 있으면 경고 메시지 리스트를 반환한다."""
        return []

    def format_result(
        self,
        *,
        operation_id: str | None,
        raw_result: dict[str, Any],
    ) -> dict[str, Any]:
        """도메인별 결과 포맷팅. 기본은 pass-through."""
        return raw_result

    def suggest_retry_strategy(
        self,
        *,
        operation_id: str | None,
        error_result: dict[str, Any],
    ) -> str | None:
        """도메인별 재시도 전략 제안. None이면 기본 policy 사용."""
        return None
