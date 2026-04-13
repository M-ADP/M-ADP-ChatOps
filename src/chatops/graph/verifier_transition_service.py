from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifierTransitionService:
    def route(
        self,
        *,
        verifier_decision: dict[str, object] | None,
        policy_decision: dict[str, object] | None,
    ) -> str:
        decision = str((verifier_decision or {}).get("decision") or "stop")
        allow_retry = bool((policy_decision or {}).get("allow_retry", False))

        if decision == "retry":
            return "retry" if allow_retry else "escalate"
        if decision in {"success", "clarify", "escalate", "stop"}:
            return decision
        return "stop"
