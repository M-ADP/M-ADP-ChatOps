from __future__ import annotations

import json
import logging

from chatops.services.decision_trace import log_decision_trace


def _parse_trace_log(record: logging.LogRecord) -> dict[str, object]:
    return json.loads(record.getMessage().split(" ", 1)[1])


def test_log_decision_trace_emits_structured_payload(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.decision_trace")

    log_decision_trace(
        stage="conversation_router",
        request_id=101,
        session_id=202,
        user_id="user-1",
        decision="small_talk",
        reason="exact social match",
        data={"social_score": 0.98, "task_score": 0.05},
    )

    trace_logs = [record for record in caplog.records if record.name == "chatops.decision_trace"]
    assert trace_logs
    payload = _parse_trace_log(trace_logs[-1])
    assert payload["event"] == "chatops.decision_trace"
    assert payload["stage"] == "conversation_router"
    assert payload["request_id"] == 101
    assert payload["session_id"] == 202
    assert payload["user_id"] == "user-1"
    assert payload["decision"] == "small_talk"
    assert payload["reason"] == "exact social match"
    assert payload["data"]["social_score"] == 0.98
    assert payload["data"]["task_score"] == 0.05


def test_log_decision_trace_truncates_long_message_fields(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.decision_trace")

    log_decision_trace(
        stage="preview_request",
        request_id=303,
        session_id=404,
        user_id="user-2",
        decision="command",
        reason="classified by llm",
        data={"message_text": "x" * 600},
    )

    trace_logs = [record for record in caplog.records if record.name == "chatops.decision_trace"]
    assert trace_logs
    payload = _parse_trace_log(trace_logs[-1])
    assert len(payload["data"]["message_text"]) < 600
    assert payload["data"]["message_text"].endswith("...")
