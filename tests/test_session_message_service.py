from __future__ import annotations

from chatops.graph.session_message_service import SessionMessageService


def test_session_message_service_uses_last_effective_message_for_follow_up() -> None:
    service = SessionMessageService()

    effective = service.effective_message_text(
        {
            "message_text": "메모리는 0.5야 디스크는 10이야",
            "session_context": {
                "last_effective_message_text": "프로젝트 하나 만들어줘\n이름은 demo야 cpu는 1이야",
                "last_request_status": "input_required",
            },
        }
    )

    assert effective == "프로젝트 하나 만들어줘\n이름은 demo야 cpu는 1이야\n메모리는 0.5야 디스크는 10이야"


def test_session_message_service_does_not_continue_irrelevant_message() -> None:
    service = SessionMessageService()

    effective = service.effective_message_text(
        {
            "message_text": "안녕",
            "session_context": {
                "last_message_text": "프로젝트 하나 만들어줘",
                "last_request_status": "input_required",
            },
        }
    )

    assert effective == "안녕"


def test_session_message_service_continues_textual_follow_up_after_ambiguity() -> None:
    service = SessionMessageService()

    effective = service.effective_message_text(
        {
            "message_text": "애플리케이션 생성",
            "session_context": {
                "last_message_text": "생성해줘",
                "last_request_status": "ambiguous",
            },
        }
    )

    assert effective == "생성해줘\n앱 생성"
