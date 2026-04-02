from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx

INQUIRY_MARKERS = ("방법", "어떻게", "가이드", "설명", "사용법")
COMMAND_MARKERS = (
    "생성",
    "삭제",
    "수정",
    "변경",
    "추가",
    "제거",
    "중지",
    "재시작",
    "배포",
    "실행",
    "등록",
    "지워",
    "바꿔",
    "고쳐",
)
QUERY_MARKERS = ("목록", "리스트", "조회", "상태", "보여", "알려", "확인", "트래픽", "로그", "상세")
INTERNAL_OPERATION_SUMMARY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")


class LLMService(Protocol):
    def classify(self, message_text: str) -> dict[str, Any]: ...

    def answer_inquiry(
        self,
        message_text: str,
        supported_operations: list[dict[str, Any]] | None = None,
    ) -> str: ...

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
        try:
            content = self._chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 요청 분류기다. 사용자 메시지를 inquiry, query, command 중 하나로만 분류한다. "
                            "JSON 객체만 반환하고 키는 request_type, intent, classification_reason, classification_confidence, "
                            "operation_candidates, is_ambiguous, missing_slots, needs_confirmation를 사용한다. "
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
                "operation_candidates": list(parsed.get("operation_candidates", [])),
                "is_ambiguous": bool(parsed.get("is_ambiguous", False)),
                "missing_slots": list(parsed.get("missing_slots", [])),
                "needs_confirmation": bool(parsed.get("needs_confirmation", False)),
            }
            return self._apply_classification_guardrails(message_text, result)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
            return self._fallback_classification(message_text)

    def answer_inquiry(
        self,
        message_text: str,
        supported_operations: list[dict[str, Any]] | None = None,
    ) -> str:
        if supported_operations == []:
            return "현재 지원하지 않는 기능입니다. 지원되는 프로젝트, 앱, 모니터링 조회 및 변경 작업만 요청할 수 있습니다."
        try:
            registry_context = self._format_inquiry_context(supported_operations)
            return self._chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 운영용 ChatOps 도우미다. 반드시 제공된 registry context만 근거로 답한다. "
                            "지원하지 않는 기능은 지원하지 않는다고 명확히 답하고, 없는 기능을 있다고 말하지 않는다. "
                            "답변은 짧고 직접적으로 작성한다."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"사용자 문의: {message_text}\nregistry context:\n{registry_context}",
                    },
                ]
            )
        except httpx.HTTPError:
            return self._fallback_inquiry_answer(message_text, supported_operations)

    def interpret_query_result(self, message_text: str, raw_result: dict[str, Any]) -> str:
        try:
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
        except httpx.HTTPError:
            return self._fallback_query_interpretation(raw_result)

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        try:
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
        except httpx.HTTPError:
            return self._fallback_command_plan(operation_ids)

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
            "operation_candidates": list(result.get("operation_candidates", [])),
            "is_ambiguous": bool(result.get("is_ambiguous", False)),
            "missing_slots": list(result.get("missing_slots", [])),
            "needs_confirmation": forced_type == "command",
        }

    def _fallback_classification(self, message_text: str) -> dict[str, Any]:
        normalized = message_text.lower()
        if any(marker in normalized for marker in INQUIRY_MARKERS):
            request_type = "inquiry"
            intent = "answer_inquiry"
        elif any(marker in normalized for marker in COMMAND_MARKERS):
            request_type = "command"
            intent = "execute_command"
        else:
            request_type = "query"
            intent = "query_status"
        return {
            "request_type": request_type,
            "intent": intent,
            "classification_reason": "LLM fallback 분류",
            "classification_confidence": 0.7,
            "operation_candidates": [],
            "is_ambiguous": False,
            "missing_slots": [],
            "needs_confirmation": request_type == "command",
        }

    def _fallback_query_interpretation(self, raw_result: dict[str, Any]) -> str:
        summary = raw_result.get("summary")
        if isinstance(summary, str) and summary.strip():
            if INTERNAL_OPERATION_SUMMARY_PATTERN.match(summary.strip()):
                return "조회 결과를 확인했습니다."
            return summary
        return "조회 결과를 확인했습니다."

    def _fallback_inquiry_answer(
        self,
        message_text: str,
        supported_operations: list[dict[str, Any]] | None = None,
    ) -> str:
        if supported_operations == []:
            return "현재 지원하지 않는 기능입니다. 지원되는 프로젝트, 앱, 모니터링 조회 및 변경 작업만 요청할 수 있습니다."
        if supported_operations:
            primary = supported_operations[0]
            capability = str(primary.get("capability") or primary.get("id") or "요청 작업")
            important_inputs = [str(item) for item in primary.get("important_inputs", []) if str(item).strip()]
            inputs_suffix = f" 필요한 정보는 {', '.join(important_inputs)}입니다." if important_inputs else ""
            approval_suffix = " 이 작업은 승인 후 실행됩니다." if primary.get("requires_confirmation") else ""
            return f"지원되는 작업입니다. {capability} 요청으로 처리할 수 있습니다.{inputs_suffix}{approval_suffix}"
        if "프로젝트" in message_text and any(marker in message_text for marker in ("생성", "만들")):
            return "프로젝트 이름과 리소스 값을 알려주시면 생성 계획을 준비합니다."
        return "요청 내용을 확인했습니다. 필요한 값을 알려주시면 다음 단계로 진행합니다."

    def _fallback_command_plan(self, operation_ids: list[str]) -> str:
        target = operation_ids[0] if operation_ids else "작업"
        return f"실행 계획\n- 요청한 작업({target})을 진행합니다.\n실행할까요?"

    def _format_inquiry_context(self, supported_operations: list[dict[str, Any]] | None) -> str:
        if not supported_operations:
            return "지원 후보 없음"
        lines: list[str] = []
        for operation in supported_operations:
            capability = str(operation.get("capability") or operation.get("id") or "unknown")
            important_inputs = [str(item) for item in operation.get("important_inputs", []) if str(item).strip()]
            line = f"- capability: {capability}"
            if important_inputs:
                line += f" | important_inputs: {', '.join(important_inputs)}"
            if operation.get("requires_confirmation"):
                line += " | requires_confirmation: true"
            lines.append(line)
        return "\n".join(lines)
