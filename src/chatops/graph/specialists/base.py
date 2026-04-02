from __future__ import annotations

from dataclasses import dataclass


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
