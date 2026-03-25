"""Tests for approval/rejection/correction intent detection."""

from __future__ import annotations

import pytest

from chatops.services.approval_intent import ApprovalIntent, detect_approval_intent


@pytest.mark.parametrize("message", [
    "응",
    "네",
    "좋아",
    "실행해",
    "실행해줘",
    "진행해",
    "진행해줘",
    "그래",
    "ㅇㅇ",
    "ok",
    "yes",
    "y",
    "해줘",
])
def test_detects_approval(message: str) -> None:
    assert detect_approval_intent(message) == ApprovalIntent.APPROVE


@pytest.mark.parametrize("message", [
    "아니",
    "취소해",
    "취소해줘",
    "하지마",
    "하지 마",
    "안 해",
    "됐어",
    "ㄴㄴ",
    "no",
    "n",
    "그만",
    "중단해",
])
def test_detects_rejection(message: str) -> None:
    assert detect_approval_intent(message) == ApprovalIntent.REJECT


@pytest.mark.parametrize("message", [
    "아니 CPU는 2로 해줘",
    "근데 메모리는 1기가로 해줘",
    "디스크는 20으로 바꿔줘",
    "이름은 demo 말고 chatops로 해줘",
    "CPU가 아니라 2로 수정해줘",
    "아니 이름은 renamed로 해줘",
])
def test_detects_correction(message: str) -> None:
    assert detect_approval_intent(message) == ApprovalIntent.CORRECTION


@pytest.mark.parametrize("message", [
    "프로젝트 하나 만들어줘",
    "앱 목록 보여줘",
    "",
    "   ",
])
def test_returns_unknown_for_unrelated_messages(message: str) -> None:
    assert detect_approval_intent(message) == ApprovalIntent.UNKNOWN
