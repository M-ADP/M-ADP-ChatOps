"""Agent Loop용 상태 정의.

고정 워크플로우의 GraphState(62개 필드)와 달리,
Agent Loop는 messages 히스토리 기반으로 동작하므로 최소한의 메타데이터만 유지한다.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict


def _append_messages(left: list | None, right: list | None) -> list:
    """Bedrock dict 형태를 유지하는 메시지 누적 reducer.

    LangGraph의 add_messages는 dict를 LangChain HumanMessage 등으로 변환하여
    boto3 Bedrock API 호출 시 ParamValidationError를 유발한다.
    이 reducer는 단순 append로 dict 형태를 보존한다.
    """
    return (left or []) + list(right or [])


class AgentState(TypedDict, total=False):
    # 신원
    request_id: int
    session_id: int
    user_id: str
    user_role: str | None
    org_id: str | None

    # 메시지 히스토리 — Agent Loop의 핵심.
    # system + user + assistant(tool_use) + user(tool_result) 메시지가 누적된다.
    messages: Annotated[list, _append_messages]

    # 세션 컨텍스트 (엔티티 메모리, 후속 참조)
    session_context: dict[str, Any] | None

    # 안전/승인 — safety_gate가 interrupt 전에 저장
    pending_tool_call: dict[str, Any] | None
    approval_granted: bool | str

    # 추적
    request_status: str
    executed_operations: list[dict[str, Any]]

    # 관측성
    execution_audit: dict[str, Any] | None
    task_snapshot: dict[str, Any] | None

    # 최종 응답 (done 시 LLM 텍스트)
    final_response: str | None

    # TTL
    created_at: str | None
    expires_at: str | None
