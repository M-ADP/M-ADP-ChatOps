from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chatops.domain.enums import RequestStatus


@dataclass(frozen=True)
class SessionMessageService:
    def effective_message_text(self, state: dict[str, Any]) -> str:
        message_text = state["message_text"]
        session_context = state.get("session_context") or {}
        if not self.should_continue_previous_request(message_text, session_context):
            return message_text

        last_effective_message_text = session_context.get("last_effective_message_text")
        if isinstance(last_effective_message_text, str) and last_effective_message_text.strip():
            return f"{last_effective_message_text}\n{message_text}".strip()

        last_message_text = session_context.get("last_message_text")
        if not isinstance(last_message_text, str) or not last_message_text.strip():
            return message_text
        return f"{last_message_text}\n{message_text}".strip()

    def should_continue_previous_request(self, message_text: str, session_context: dict[str, Any]) -> bool:
        last_status = session_context.get("last_request_status")
        if last_status not in (RequestStatus.INPUT_REQUIRED.value, RequestStatus.PENDING_APPROVAL.value):
            return False
        if not isinstance(message_text, str) or not message_text.strip():
            return False

        supplement_markers = (
            "이름",
            "프로젝트 이름",
            "앱 이름",
            "애플리케이션 이름",
            "cpu",
            "max_cpu",
            "memory",
            "메모리",
            "max_memory",
            "disk",
            "디스크",
            "max_disk",
            "port",
            "포트",
            "owner",
            "repository",
            "repo",
            "branch",
            "브랜치",
            "깃허브",
            "github",
            "=",
            ":",
            "그거",
            "이거",
            "아까",
            "방금",
            "닉네임",
            "대상 사용자",
            "멤버",
            "소유권",
            "바꿔",
            "변경",
            "수정",
            "고쳐",
            "대신",
            "말고",
            "로 해",
            "이 아니라",
            "가 아니라",
        )
        return any(marker in message_text for marker in supplement_markers)
