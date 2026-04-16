from __future__ import annotations

from chatops.services.easter_egg_service import EasterEggService


def test_easter_egg_service_appends_matched_messages_to_response() -> None:
    service = EasterEggService(
        {
            "조재민": "조재민 이스터에그",
            "박동현": "박동현 이스터에그",
        }
    )

    result = service.decorate_response(
        message_text="조재민이랑 박동현 상태 알려줘",
        response_text="상태를 조회했습니다.",
    )

    assert result == "상태를 조회했습니다.\n\n조재민 이스터에그\n박동현 이스터에그"


def test_easter_egg_service_leaves_response_unchanged_without_registered_message() -> None:
    service = EasterEggService({"조재민": ""})

    result = service.decorate_response(
        message_text="조재민 상태 알려줘",
        response_text="상태를 조회했습니다.",
    )

    assert result == "상태를 조회했습니다."
