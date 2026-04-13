from __future__ import annotations

import re
from typing import Any

from chatops.graph.specialists.base import BaseSpecialist

_APP_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
_CPU_LIMIT = 8
_MEMORY_LIMIT_MB = 16384


class ApplicationSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="application")

    def validate_inputs(
        self,
        *,
        operation_id: str | None,
        resolved_inputs: dict[str, object] | None,
    ) -> list[str]:
        warnings: list[str] = []
        inputs = resolved_inputs or {}
        references = inputs.get("references") or {}

        if operation_id == "application.create_apps":
            app_name = str(references.get("application_name", "")).strip()
            if app_name and not _APP_NAME_PATTERN.match(app_name):
                warnings.append(
                    f"앱 이름 '{app_name}'에 허용되지 않는 문자가 있습니다. "
                    "소문자, 숫자, 하이픈만 사용 가능하며 소문자로 시작해야 합니다."
                )

        if operation_id == "application.patch_apps_resources":
            body = inputs.get("body") or {}
            if isinstance(body, dict):
                cpu = body.get("cpu")
                memory = body.get("memory")
                if cpu is not None:
                    try:
                        if float(cpu) > _CPU_LIMIT:
                            warnings.append(
                                f"CPU {cpu}코어는 상한({_CPU_LIMIT}코어)을 초과합니다. "
                                "실제 적용 가능한 값인지 확인하세요."
                            )
                    except (TypeError, ValueError):
                        pass
                if memory is not None:
                    try:
                        if float(memory) > _MEMORY_LIMIT_MB:
                            warnings.append(
                                f"메모리 {memory}MB는 상한({_MEMORY_LIMIT_MB}MB)을 초과합니다. "
                                "실제 적용 가능한 값인지 확인하세요."
                            )
                    except (TypeError, ValueError):
                        pass

        return warnings

    def format_result(
        self,
        *,
        operation_id: str | None,
        raw_result: dict[str, Any],
    ) -> dict[str, Any]:
        if operation_id == "application.get_apps_status":
            data = raw_result.get("data") or raw_result.get("result") or {}
            if isinstance(data, dict):
                status = data.get("status", "unknown")
                result = dict(raw_result)
                result.setdefault("formatted_summary", f"앱 상태: {status}")
                return result
        return raw_result

    def suggest_retry_strategy(
        self,
        *,
        operation_id: str | None,
        error_result: dict[str, Any],
    ) -> str | None:
        status_code = int(error_result.get("status_code", 0))
        if operation_id == "application.get_apps_logs" and status_code == 504:
            return "앱 로그 조회가 타임아웃됐습니다. 시간 범위를 줄여 다시 시도합니다."
        if status_code in (502, 503, 504):
            return "앱 서버 일시 장애입니다. 잠시 후 다시 시도합니다."
        return None
