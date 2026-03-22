from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

INQUIRY_MARKERS = ("방법", "어떻게", "가이드", "설명", "사용법")
COMMAND_MARKERS = ("생성", "삭제", "수정", "변경", "추가", "제거", "중지", "재시작", "배포", "실행", "등록")
QUERY_MARKERS = ("목록", "리스트", "조회", "상태", "보여", "알려", "확인", "트래픽", "로그", "상세")


class LLMService(Protocol):
    def classify(self, message_text: str) -> dict[str, Any]: ...

    def answer_inquiry(self, message_text: str) -> str: ...

    def interpret_query_result(self, message_text: str, raw_result: dict[str, Any]) -> str: ...

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str: ...


class GroqLLMService:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client or httpx.Client(timeout=timeout_seconds)
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def classify(self, message_text: str) -> dict[str, Any]:
        content = self._chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 요청 분류기다. 사용자 메시지를 inquiry, query, command 중 하나로만 분류한다. "
                        "JSON 객체만 반환하고 키는 request_type, intent, classification_reason, classification_confidence를 사용한다. "
                        "classification_confidence는 0과 1 사이 숫자다."
                    ),
                },
                {"role": "user", "content": message_text},
            ],
            response_format={"type": "json_object"},
        )
        parsed = json.loads(content)
        result = {
            "request_type": parsed["request_type"],
            "intent": parsed.get("intent", ""),
            "classification_reason": parsed.get("classification_reason", ""),
            "classification_confidence": float(parsed.get("classification_confidence", 0.0)),
        }
        return self._apply_classification_guardrails(message_text, result)

    def answer_inquiry(self, message_text: str) -> str:
        return self._chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "당신은 운영용 ChatOps 도우미다. 사용자의 문의에 짧고 직접적으로 답한다.",
                },
                {"role": "user", "content": message_text},
            ]
        )

    def interpret_query_result(self, message_text: str, raw_result: dict[str, Any]) -> str:
        return self._chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "당신은 조회 결과를 해석하는 운영 도우미다. 결과를 짧게 요약한다.",
                },
                {
                    "role": "user",
                    "content": f"사용자 요청: {message_text}\n조회 결과: {json.dumps(raw_result, ensure_ascii=False)}",
                },
            ]
        )

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        return self._chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "당신은 명령 실행 계획 작성기다. 실행 전에 보여줄 짧은 계획을 한국어로 작성한다.",
                },
                {
                    "role": "user",
                    "content": f"사용자 요청: {message_text}\n후보 작업: {', '.join(operation_ids)}",
                },
            ]
        )

    def _chat_completion(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, str] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        response = self.client.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        return str(body["choices"][0]["message"]["content"]).strip()

    def _apply_classification_guardrails(
        self,
        message_text: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = message_text.lower()
        forced_type: str | None = None
        forced_intent: str | None = None

        if any(marker in normalized for marker in INQUIRY_MARKERS):
            forced_type = "inquiry"
            forced_intent = "answer_inquiry"
        elif any(marker in normalized for marker in COMMAND_MARKERS):
            forced_type = "command"
            forced_intent = "execute_command"
        elif any(marker in normalized for marker in QUERY_MARKERS):
            forced_type = "query"
            forced_intent = "query_status"

        if forced_type is None or forced_type == result["request_type"]:
            return result

        return {
            "request_type": forced_type,
            "intent": forced_intent,
            "classification_reason": f"정책 가드레일로 {forced_type} 요청으로 조정",
            "classification_confidence": max(float(result.get("classification_confidence", 0.0)), 0.99),
        }
