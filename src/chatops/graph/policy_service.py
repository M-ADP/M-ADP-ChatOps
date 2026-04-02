from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyService:
    max_retry_count: int = 2

    def evaluate(
        self,
        *,
        operation_id: str | None,
        risk_level: str | None,
        retry_count: int,
        superseded: bool,
    ) -> dict[str, object]:
        if superseded:
            return {
                "decision": "stop",
                "requires_approval": False,
                "allow_execute": False,
                "allow_retry": False,
            }
        if retry_count >= self.max_retry_count:
            return {
                "decision": "escalate",
                "requires_approval": bool(risk_level == "high"),
                "allow_execute": True,
                "allow_retry": False,
            }
        destructive = any(token in (operation_id or "") for token in ("delete", "remove", "transfer"))
        requires_approval = bool(risk_level == "high" or destructive)
        return {
            "decision": "execute",
            "requires_approval": requires_approval,
            "allow_execute": True,
            "allow_retry": True,
        }
