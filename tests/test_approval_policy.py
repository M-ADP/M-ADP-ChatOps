from __future__ import annotations

from chatops.graph.approval_policy import ApprovalPolicyService


def test_approval_policy_builds_structured_confirmation_payload() -> None:
    service = ApprovalPolicyService()

    payload = service.build_confirmation_payload(
        operation_id="project.remove_member",
        resolved_inputs={"references": {"project_name": "demo", "target_nickname": "alice"}},
    )

    assert payload == {
        "operation": "project.remove_member",
        "project_name": "demo",
        "target_user": "alice",
    }


def test_approval_policy_validates_structured_confirmation_text() -> None:
    service = ApprovalPolicyService()
    expected_payload = {
        "operation": "project.remove_member",
        "project_name": "demo",
        "target_user": "alice",
    }

    assert service.matches_confirmation(
        '{"operation":"project.remove_member","project_name":"demo","target_user":"alice"}',
        expected_payload,
    ) is True
    assert service.matches_confirmation(
        '{"operation":"project.remove_member","project_name":"demo"}',
        expected_payload,
    ) is False
