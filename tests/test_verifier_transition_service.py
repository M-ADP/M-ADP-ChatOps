from __future__ import annotations

from chatops.graph.verifier_transition_service import VerifierTransitionService


def test_transition_service_maps_retry_with_budget_to_retry_route() -> None:
    route = VerifierTransitionService().route(
        verifier_decision={"decision": "retry"},
        policy_decision={"allow_retry": True},
    )

    assert route == "retry"


def test_transition_service_maps_retry_without_budget_to_escalate_route() -> None:
    route = VerifierTransitionService().route(
        verifier_decision={"decision": "retry"},
        policy_decision={"allow_retry": False},
    )

    assert route == "escalate"


def test_transition_service_preserves_non_retry_terminal_decisions() -> None:
    service = VerifierTransitionService()

    assert service.route(verifier_decision={"decision": "success"}, policy_decision={}) == "success"
    assert service.route(verifier_decision={"decision": "clarify"}, policy_decision={}) == "clarify"
    assert service.route(verifier_decision={"decision": "escalate"}, policy_decision={}) == "escalate"
    assert service.route(verifier_decision={"decision": "stop"}, policy_decision={}) == "stop"
