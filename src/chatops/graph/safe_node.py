"""P0: Graph 노드 공통 예외 처리 래퍼.

모든 graph 노드에 적용하여 예외가 사용자에게 raw stack trace로
전파되는 것을 방지한다.
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable

import httpx

from chatops.domain.enums import RequestStatus
from chatops.graph.state import GraphState
from chatops.services.downstream_dispatcher import EntityResolutionError

logger = logging.getLogger(__name__)


class DownstreamForbiddenError(Exception):
    """Downstream API가 403을 반환한 경우."""
    pass


class DownstreamNotFoundError(Exception):
    """Downstream API가 404를 반환한 경우."""
    pass


# 예외 유형별 사용자 메시지 + error_code
_ERROR_MAP: list[tuple[type[BaseException], str, str]] = [
    (
        httpx.TimeoutException,
        "AI 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.",
        "LLM_TIMEOUT",
    ),
    (
        EntityResolutionError,
        "대상을 찾을 수 없습니다. 이름을 다시 확인해주세요.",
        "ENTITY_NOT_FOUND",
    ),
    (
        DownstreamForbiddenError,
        "권한이 부족하여 요청을 수행할 수 없습니다.",
        "FORBIDDEN",
    ),
    (
        DownstreamNotFoundError,
        "요청한 리소스를 찾을 수 없습니다.",
        "RESOURCE_NOT_FOUND",
    ),
    (
        (httpx.HTTPStatusError, httpx.HTTPError),
        "외부 서비스 연결에 실패했습니다. 잠시 후 다시 시도해주세요.",
        "DOWNSTREAM_ERROR",
    ),
]


def _classify_error(exc: BaseException) -> tuple[str, str]:
    """예외를 사용자 메시지와 error_code로 변환한다."""
    for exc_type, message, code in _ERROR_MAP:
        if isinstance(exc, exc_type):
            return message, code
    return (
        "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "INTERNAL_ERROR",
    )


def safe_node(func: Callable[..., GraphState]) -> Callable[..., GraphState]:
    """Graph 노드에 예외 처리를 적용하는 데코레이터.

    예외 발생 시:
    - logger.error로 상세 로그 기록
    - 사용자에게는 친화적 메시지만 반환
    - request_status를 FAILED로 전이
    """

    @functools.wraps(func)
    def wrapper(self: Any, state: GraphState) -> GraphState:
        try:
            return func(self, state)
        except Exception as exc:
            user_message, error_code = _classify_error(exc)
            logger.error(
                "Node '%s' failed for request_id=%s: %s",
                func.__name__,
                state.get("request_id"),
                exc,
                exc_info=True,
            )
            return {
                "final_response": user_message,
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
                "error_code": error_code,
            }

    return wrapper
