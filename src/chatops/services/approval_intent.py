"""Detect approval, rejection, or correction intent from user messages."""

from __future__ import annotations

from enum import Enum


class ApprovalIntent(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    CORRECTION = "correction"
    UNKNOWN = "unknown"


APPROVE_MARKERS = (
    "응",
    "어",
    "네",
    "예",
    "좋아",
    "그래",
    "맞아",
    "확인",
    "실행해",
    "실행해줘",
    "진행해",
    "진행해줘",
    "해줘",
    "ㅇㅇ",
    "ㅇㅋ",
    "ok",
    "yes",
    "y",
)

REJECT_MARKERS = (
    "아니",
    "아니야",
    "아니요",
    "취소",
    "취소해",
    "취소해줘",
    "안 해",
    "하지 마",
    "하지마",
    "됐어",
    "그만",
    "중단",
    "중단해",
    "ㄴㄴ",
    "no",
    "n",
)

CORRECTION_MARKERS = (
    "아니 ",
    "근데 ",
    "그런데 ",
    "바꿔",
    "변경",
    "수정",
    "고쳐",
    "대신",
    "말고",
    "로 해",
    "으로 해",
    "이 아니라",
    "가 아니라",
)


def detect_approval_intent(message_text: str) -> ApprovalIntent:
    """Classify a user message as approval, rejection, correction, or unknown.

    The order of checks matters:
    1. Correction first — corrections may contain reject-like words (e.g. '아니 CPU는 2로 해줘')
    2. Rejection second — pure rejections without correction markers
    3. Approval last — short affirmative messages
    """
    if not isinstance(message_text, str) or not message_text.strip():
        return ApprovalIntent.UNKNOWN

    normalized = message_text.strip().lower()

    # Correction: contains correction markers AND has parameter-like content
    if _has_correction_markers(normalized) and _has_parameter_content(normalized):
        return ApprovalIntent.CORRECTION

    # Pure rejection
    if _is_pure_rejection(normalized):
        return ApprovalIntent.REJECT

    # Pure approval
    if _is_pure_approval(normalized):
        return ApprovalIntent.APPROVE

    return ApprovalIntent.UNKNOWN


def _has_correction_markers(text: str) -> bool:
    return any(marker in text for marker in CORRECTION_MARKERS)


def _has_parameter_content(text: str) -> bool:
    """Check if message contains parameter-like values (numbers, key=value, field names)."""
    param_indicators = (
        "cpu", "메모리", "memory", "디스크", "disk", "포트", "port",
        "이름", "name", "=", ":", "기가", "gb", "mb",
        "owner", "repository", "repo", "branch", "브랜치",
    )
    return any(indicator in text.lower() for indicator in param_indicators)


def _is_pure_rejection(text: str) -> bool:
    # Exact match for short rejections
    if text in REJECT_MARKERS:
        return True
    # Starts with rejection marker and is short (not a correction)
    for marker in REJECT_MARKERS:
        if text.startswith(marker) and len(text) < len(marker) + 15:
            return True
    return False


def _is_pure_approval(text: str) -> bool:
    # Exact match for short approvals
    if text in APPROVE_MARKERS:
        return True
    # Starts with approval marker and is short
    for marker in APPROVE_MARKERS:
        if text.startswith(marker) and len(text) < len(marker) + 10:
            return True
    return False
