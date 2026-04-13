from __future__ import annotations

from typing import Any

from chatops.graph.specialists.base import BaseSpecialist


class MonitoringSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="monitoring")

    def format_result(
        self,
        *,
        operation_id: str | None,
        raw_result: dict[str, Any],
    ) -> dict[str, Any]:
        if operation_id == "monitoring.get_app_deployment_traffic":
            data = raw_result.get("data") or raw_result.get("result") or {}
            if isinstance(data, dict):
                traffic = data.get("traffic")
                result = dict(raw_result)
                if traffic is not None:
                    result.setdefault("formatted_summary", f"현재 트래픽: {traffic}")
                return result
        return raw_result

    def suggest_retry_strategy(
        self,
        *,
        operation_id: str | None,
        error_result: dict[str, Any],
    ) -> str | None:
        status_code = int(error_result.get("status_code", 0))
        if status_code in (502, 503, 504):
            return "모니터링 서버 일시 장애입니다. 잠시 후 다시 시도합니다."
        return None
