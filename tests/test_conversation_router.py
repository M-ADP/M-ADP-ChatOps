from chatops.services.conversation_router import ConversationRouterService


def test_conversation_router_routes_plain_greeting_to_small_talk() -> None:
    service = ConversationRouterService()

    decision = service.decide(message_text="안녕", session_context=None)

    assert decision.route == "small_talk"
    assert decision.response is not None
    assert decision.social_score > decision.task_score


def test_conversation_router_prioritizes_task_when_follow_up_prompt_exists() -> None:
    service = ConversationRouterService()

    decision = service.decide(
        message_text="2",
        session_context={
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "choice",
                    "options": [
                        {"value": "프로젝트 생성", "label": "프로젝트 생성"},
                        {"value": "애플리케이션 생성", "label": "애플리케이션 생성"},
                    ],
                }
            }
        },
    )

    assert decision.route == "task"
    assert decision.task_score >= 0.55


def test_conversation_router_keeps_greeting_as_small_talk_even_with_follow_up_prompt() -> None:
    service = ConversationRouterService()

    decision = service.decide(
        message_text="안녕",
        session_context={
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "choice",
                    "options": [
                        {"value": "프로젝트 생성", "label": "프로젝트 생성"},
                        {"value": "애플리케이션 생성", "label": "애플리케이션 생성"},
                    ],
                }
            }
        },
    )

    assert decision.route == "small_talk"
