from __future__ import annotations

import json
import logging

from chatops.graph.verifier_service import VerifierService


def test_verifier_returns_success_for_successful_execution() -> None:
    service = VerifierService()

    decision = service.verify(
        request_type="command",
        operation_id="application.create_apps",
        execution_result={"success": True, "summary": "앱 생성 완료", "status_code": 200},
    )

    assert decision["decision"] == "success"
    assert decision["follow_up_action"] == "complete"


def test_verifier_requests_retry_for_server_side_failure() -> None:
    service = VerifierService()

    decision = service.verify(
        request_type="command",
        operation_id="application.create_apps",
        execution_result={"success": False, "summary": "일시적 오류", "status_code": 503},
    )

    assert decision["decision"] == "retry"
    assert decision["follow_up_action"] == "retry"


def test_verifier_requests_clarification_for_input_error() -> None:
    service = VerifierService()

    decision = service.verify(
        request_type="command",
        operation_id="application.create_apps",
        execution_result={"success": False, "summary": "입력값이 부족합니다.", "status_code": 422},
    )

    assert decision["decision"] == "clarify"
    assert decision["follow_up_action"] == "fill_inputs"


def test_verifier_logs_decision_trace(caplog) -> None:
    service = VerifierService()
    caplog.set_level(logging.INFO, logger="chatops.decision_trace")

    decision = service.verify(
        request_type="command",
        operation_id="application.create_apps",
        execution_result={"success": False, "summary": "입력값이 부족합니다.", "status_code": 422},
    )

    assert decision["decision"] == "clarify"
    trace_logs = [record for record in caplog.records if record.name == "chatops.decision_trace"]
    payloads = [json.loads(record.getMessage().split(" ", 1)[1]) for record in trace_logs]
    verifier_payload = next(payload for payload in payloads if payload["stage"] == "verifier")
    assert verifier_payload["decision"] == "clarify"
    assert verifier_payload["data"]["operation_id"] == "application.create_apps"
    assert verifier_payload["data"]["status_code"] == 422


def test_verifier_escalates_for_permission_error() -> None:
    service = VerifierService()

    decision = service.verify(
        request_type="query",
        operation_id="project.list_projects",
        execution_result={"success": False, "summary": "권한이 없습니다.", "status_code": 403},
    )

    assert decision["decision"] == "escalate"
    assert decision["follow_up_action"] == "human_review"
