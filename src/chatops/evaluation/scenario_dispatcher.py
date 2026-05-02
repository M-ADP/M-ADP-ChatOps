"""평가용 mock dispatcher.

로컬 환경에서 downstream API에 접근할 수 없으므로,
operation_id별 canned response를 반환하는 dispatcher로 대체한다.
시나리오마다 다른 응답을 주입할 수 있도록 set_responses()를 제공한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_DEFAULT_SUCCESS = {"summary": "ok", "success": True}


@dataclass
class ScenarioDispatcher:
    """operation_id → canned response 매핑 dispatcher.

    실제 DownstreamDispatcher와 동일한 interface(execute_query, execute_command)를 제공한다.
    """

    response_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    executed_operation_ids: list[str] = field(default_factory=list)
    last_resolved_inputs: dict[str, Any] | None = None

    def set_responses(self, response_map: dict[str, dict[str, Any]] | None) -> None:
        self.response_map = dict(response_map or {})

    def reset(self) -> None:
        self.executed_operation_ids.clear()
        self.last_resolved_inputs = None

    async def execute_query(
        self,
        operation: Any,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del user_id, user_role, org_id
        return self._dispatch(operation, resolved_inputs)

    async def execute_command(
        self,
        operation: Any,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del user_id, user_role, org_id
        return self._dispatch(operation, resolved_inputs)

    def _dispatch(self, operation: Any, resolved_inputs: dict[str, Any] | None) -> dict[str, Any]:
        operation_id = getattr(operation, "id", str(operation))
        self.executed_operation_ids.append(operation_id)
        self.last_resolved_inputs = dict(resolved_inputs or {})
        canned = self.response_map.get(operation_id)
        if canned is None:
            return dict(_DEFAULT_SUCCESS)
        return dict(canned)
