from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from chatops.services.request_normalizer import RequestNormalizerService


_SOCIAL_EXACT = {
    "안녕",
    "ㅎㅇ",
    "하이",
    "hello",
    "hey",
    "반가워",
    "고마워",
    "감사",
    "thanks",
    "thank you",
    "ㅋㅋ",
    "ㅎㅎ",
}
_SOCIAL_MARKERS = ("안녕", "반가", "고마", "감사", "hello", "hey", "thanks", "ㅋㅋ", "ㅎㅎ")
_TASK_MARKERS = (
    "생성",
    "삭제",
    "수정",
    "변경",
    "조회",
    "목록",
    "상태",
    "추가",
    "제거",
    "승인",
    "취소",
    "실행",
    "project",
    "app",
    "프로젝트",
    "앱",
    "애플리케이션",
    "어플리케이션",
    "cpu",
    "memory",
    "disk",
    "port",
)
_SINGLE_CHOICE_PATTERN = re.compile(r"^[0-9a-z]$", re.IGNORECASE)


@dataclass(frozen=True)
class ConversationRouteDecision:
    route: str
    social_score: float
    task_score: float
    response: str | None = None


@dataclass(frozen=True)
class ConversationRouterService:
    normalizer: RequestNormalizerService = RequestNormalizerService()

    def decide(
        self,
        *,
        message_text: str,
        session_context: dict[str, Any] | None,
    ) -> ConversationRouteDecision:
        normalized = self.normalizer.normalize(message_text).lower()
        explicit_social = normalized in _SOCIAL_EXACT
        explicit_task = self._has_explicit_task_signal(normalized)

        if explicit_social and not explicit_task:
            return ConversationRouteDecision(
                route="small_talk",
                social_score=0.98,
                task_score=0.05,
                response=self._small_talk_response(normalized),
            )

        social_score = self._social_score(normalized)
        task_score = self._task_score(normalized, session_context)

        if social_score >= 0.8 and task_score < 0.35:
            return ConversationRouteDecision(
                route="small_talk",
                social_score=social_score,
                task_score=task_score,
                response=self._small_talk_response(normalized),
            )
        if social_score >= 0.55 and task_score < 0.55:
            return ConversationRouteDecision(
                route="bridge",
                social_score=social_score,
                task_score=task_score,
                response="무엇을 도와드릴까요? 프로젝트 생성, 앱 생성, 목록 조회 중에 말씀해 주세요.",
            )
        return ConversationRouteDecision(route="task", social_score=social_score, task_score=task_score)

    def _social_score(self, normalized: str) -> float:
        if not normalized:
            return 0.0
        if normalized in _SOCIAL_EXACT:
            return 0.98

        marker_hits = sum(1 for marker in _SOCIAL_MARKERS if marker in normalized)
        if marker_hits == 0:
            return 0.05

        base = min(0.85, 0.45 + marker_hits * 0.2)
        if len(normalized) <= 6:
            base = min(0.95, base + 0.1)
        return base

    def _task_score(self, normalized: str, session_context: dict[str, Any] | None) -> float:
        if not normalized:
            return 0.0

        marker_hits = sum(1 for marker in _TASK_MARKERS if marker in normalized)
        score = min(0.9, 0.1 + marker_hits * 0.15)
        if "=" in normalized or ":" in normalized:
            score = min(0.95, score + 0.2)

        follow_up_prompt = self._follow_up_prompt(session_context)
        if follow_up_prompt is not None:
            score = min(0.95, score + 0.35)
            if _SINGLE_CHOICE_PATTERN.fullmatch(normalized):
                score = min(0.98, score + 0.25)
        return score

    @staticmethod
    def _follow_up_prompt(session_context: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(session_context, dict):
            return None
        task_snapshot = session_context.get("last_task_snapshot")
        if not isinstance(task_snapshot, dict):
            return None
        follow_up_prompt = task_snapshot.get("follow_up_prompt")
        if not isinstance(follow_up_prompt, dict):
            return None
        return follow_up_prompt

    @staticmethod
    def _small_talk_response(normalized: str) -> str:
        if "고마" in normalized or "감사" in normalized or "thank" in normalized:
            return "도움이 되어 다행입니다. 이어서 필요한 작업을 말씀해 주세요."
        return "안녕하세요. 무엇을 도와드릴까요? 예: 프로젝트 생성해줘, 앱 생성해줘, 프로젝트 목록 보여줘"

    @staticmethod
    def _has_explicit_task_signal(normalized: str) -> bool:
        return any(marker in normalized for marker in _TASK_MARKERS) or "=" in normalized or ":" in normalized
