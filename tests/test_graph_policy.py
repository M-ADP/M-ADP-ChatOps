from __future__ import annotations

from chatops.graph.policy_service import PolicyService


def test_policy_requires_approval_for_destructive_actions() -> None:
    service = PolicyService()

    decision = service.evaluate(
        operation_id="project.delete",
        risk_level="high",
        retry_count=0,
        superseded=False,
    )

    assert decision["requires_approval"] is True
    assert decision["allow_execute"] is True


def test_policy_blocks_superseded_requests() -> None:
    service = PolicyService()

    decision = service.evaluate(
        operation_id="project.create",
        risk_level="medium",
        retry_count=0,
        superseded=True,
    )

    assert decision["allow_execute"] is False
    assert decision["decision"] == "stop"


def test_policy_caps_retry_budget() -> None:
    service = PolicyService(max_retry_count=2)

    decision = service.evaluate(
        operation_id="application.create_apps",
        risk_level="medium",
        retry_count=2,
        superseded=False,
    )

    assert decision["allow_retry"] is False
    assert decision["decision"] == "escalate"
