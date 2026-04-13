from __future__ import annotations

from typing import Any

from chatops.graph.specialists.base import BaseSpecialist

_MIN_PROJECT_NAME_LEN = 2


class ProjectSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="project")

    def validate_inputs(
        self,
        *,
        operation_id: str | None,
        resolved_inputs: dict[str, object] | None,
    ) -> list[str]:
        warnings: list[str] = []
        inputs = resolved_inputs or {}
        references = inputs.get("references") or {}

        if operation_id == "project.create":
            name = str(references.get("project_name", "")).strip()
            if name and len(name) < _MIN_PROJECT_NAME_LEN:
                warnings.append(
                    f"프로젝트 이름 '{name}'이(가) 너무 짧습니다. "
                    f"{_MIN_PROJECT_NAME_LEN}자 이상 입력해주세요."
                )

        if operation_id == "project.transfer_ownership":
            target = str(references.get("target_nickname", "")).strip()
            if not target:
                warnings.append("소유권을 이전할 대상 사용자(닉네임)를 지정해주세요.")

        if operation_id in {"project.add_member", "project.remove_member"}:
            target = str(references.get("target_nickname", "")).strip()
            if not target:
                action = "추가할" if operation_id == "project.add_member" else "제거할"
                warnings.append(f"{action} 멤버의 닉네임을 지정해주세요.")

        return warnings

    def suggest_retry_strategy(
        self,
        *,
        operation_id: str | None,
        error_result: dict[str, Any],
    ) -> str | None:
        status_code = int(error_result.get("status_code", 0))
        if status_code == 409:
            return "리소스 충돌이 발생했습니다. 최신 상태를 확인한 후 다시 시도합니다."
        if status_code in (502, 503, 504):
            return "서버 일시 장애입니다. 잠시 후 다시 시도합니다."
        return None
