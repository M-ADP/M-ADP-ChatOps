from __future__ import annotations

import json
import re
from typing import Any, Protocol

from chatops.services.response_streaming import get_response_stream_handler

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

# 액션 + inquiry 조합 패턴 ("삭제 방법", "어떻게 만들어" 등은 inquiry로 강하게 감지)
_INQUIRY_ACTION_PATTERNS = [
    re.compile(r"(삭제|생성|수정|변경|배포|실행|추가|제거|등록)\s*(방법|어떻게|가이드|설명|사용법)"),
    re.compile(r"(방법|어떻게|가이드|설명|사용법)\s*(을|를)?\s*(알려|보여|설명|가르쳐)"),
    re.compile(r"어떻게\s+(삭제|생성|수정|변경|배포|실행|추가|제거|등록)"),
]

# 신뢰도 임계값: 이 이상이면 가드레일 스킵
_GUARDRAIL_SKIP_CONFIDENCE = 0.85
# 이 미만의 신뢰도에서만 강한 키워드 신호로 덮어씀
_GUARDRAIL_OVERRIDE_CONFIDENCE = 0.80


class LLMService(Protocol):
    def classify(self, message_text: str) -> dict[str, Any]: ...

    def answer_inquiry(
        self,
        message_text: str,
        supported_operations: list[dict[str, Any]] | None = None,
    ) -> str: ...

    def interpret_query_result(self, message_text: str, raw_result: dict[str, Any]) -> str: ...

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str: ...

    def build_plan_object(
        self,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, Any]: ...

    def verify_execution(
        self,
        execution_result: dict[str, Any],
        operation_id: str | None = None,
        message_text: str | None = None,
    ) -> dict[str, Any]: ...


class BedrockLLMService:
    def __init__(
        self,
        model_id: str,
        timeout_seconds: int,
        client: Any,
        max_tokens: int = 1024,
        guardrail_id: str | None = None,
        guardrail_version: str = "DRAFT",
    ) -> None:
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self.client = client
        self.max_tokens = max_tokens
        self.guardrail_id = guardrail_id
        self.guardrail_version = guardrail_version

    def classify(self, message_text: str) -> dict[str, Any]:
        try:
            content = self._text_response(
                system_prompt=(
                    "당신은 요청 분류기다. 사용자 메시지를 inquiry, query, command 중 하나로만 분류한다. "
                    "JSON 객체만 반환하고 키는 request_type, intent, classification_reason, classification_confidence, "
                    "operation_candidates, is_ambiguous, missing_slots, needs_confirmation를 사용한다. "
                    "classification_confidence는 0과 1 사이 숫자다."
                ),
                user_prompt=message_text,
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
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, Exception):
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
            return self._model_text_response(
                system_prompt=(
                    "당신은 운영용 ChatOps 도우미다. 반드시 제공된 registry context만 근거로 답한다. "
                    "지원하지 않는 기능은 지원하지 않는다고 명확히 답하고, 없는 기능을 있다고 말하지 않는다. "
                    "답변은 짧고 직접적으로 작성한다."
                ),
                user_prompt=f"사용자 문의: {message_text}\nregistry context:\n{registry_context}",
            )
        except Exception:
            return self._fallback_inquiry_answer(message_text, supported_operations)

    def interpret_query_result(self, message_text: str, raw_result: dict[str, Any]) -> str:
        try:
            return self._model_text_response(
                system_prompt="당신은 조회 결과를 해석하는 운영 도우미다. 결과를 짧게 요약한다.",
                user_prompt=f"사용자 요청: {message_text}\n조회 결과: {json.dumps(raw_result, ensure_ascii=False)}",
            )
        except Exception:
            return self._fallback_query_interpretation(raw_result)

    def plan_command(self, message_text: str, operation_ids: list[str]) -> str:
        try:
            return self._text_response(
                system_prompt="당신은 명령 실행 계획 작성기다. 실행 전에 보여줄 짧은 계획을 한국어로 작성한다.",
                user_prompt=f"사용자 요청: {message_text}\n후보 작업: {', '.join(operation_ids)}",
            )
        except Exception:
            return self._fallback_command_plan(operation_ids)

    def build_plan_object(
        self,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, Any]:
        try:
            content = self._text_response(
                system_prompt=(
                    "당신은 ChatOps planner다. 사용자 목표를 구조화된 JSON plan object로만 반환한다. "
                    "키는 goal, specialist, entities, constraints, candidate_steps, risk_level, required_clarifications 를 사용한다."
                ),
                user_prompt=(
                    f"사용자 요청: {message_text}\n"
                    f"request_type: {request_type}\n"
                    f"candidate_operation_ids: {', '.join(candidate_operation_ids)}"
                ),
            )
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("plan object must be a JSON object")
            return parsed
        except (json.JSONDecodeError, ValueError, TypeError, Exception):
            return self._fallback_plan_object(
                message_text=message_text,
                request_type=request_type,
                candidate_operation_ids=candidate_operation_ids,
            )

    def verify_execution(
        self,
        execution_result: dict[str, Any],
        operation_id: str | None = None,
        message_text: str | None = None,
    ) -> dict[str, Any]:
        try:
            context_parts: list[str] = []
            if operation_id:
                context_parts.append(f"실행된 작업: {operation_id}")
            if message_text:
                context_parts.append(f"사용자 요청: {message_text}")
            context = "\n".join(context_parts) if context_parts else ""
            user_prompt = (
                f"{context}\nexecution_result: {json.dumps(execution_result, ensure_ascii=False)}"
                if context
                else f"execution_result: {json.dumps(execution_result, ensure_ascii=False)}"
            )
            content = self._text_response(
                system_prompt=(
                    "당신은 ChatOps verifier다. 실행 결과를 보고 "
                    "success, retry, clarify, escalate, stop 중 하나를 고른다.\n"
                    "판단 기준:\n"
                    "- success: 결과가 요청 의도에 부합\n"
                    "- retry: 일시적 오류 (5xx, timeout)\n"
                    "- clarify: 결과가 비어있거나 요청과 불일치\n"
                    "- escalate: 권한 문제 또는 위험한 상태 감지\n"
                    "- stop: 복구 불가능한 오류\n"
                    "JSON 객체만 반환하고 키는 decision, summary, missing_inputs, follow_up_action 을 사용한다."
                ),
                user_prompt=user_prompt,
            )
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("verifier decision must be a JSON object")
            return parsed
        except (json.JSONDecodeError, ValueError, TypeError, Exception):
            return self._fallback_verifier_decision(execution_result)

    # ──────────────────────────────────────────────────
    # Agent Loop: Converse API with tool_use support
    # ──────────────────────────────────────────────────

    def _guardrail_kwargs(self) -> dict[str, Any]:
        """Bedrock Guardrails 설정이 있을 때만 kwargs를 반환한다.

        BEDROCK_GUARDRAIL_ID 환경변수가 설정되면 promptAttack 필터가 활성화된다.
        """
        if not self.guardrail_id:
            return {}
        return {
            "guardrailIdentifier": self.guardrail_id,
            "guardrailVersion": self.guardrail_version,
        }

    def converse_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tool_specs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Bedrock Converse API를 tool 정의와 함께 호출한다.

        Returns:
            {
                "stop_reason": "end_turn" | "tool_use",
                "assistant_message": dict,  # messages에 추가할 assistant 메시지
                "tool_calls": [{"tool_use_id": str, "name": str, "input": dict}],
                "text_content": str | None,
            }
        """
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
            "inferenceConfig": self._inference_config(),
            **self._guardrail_kwargs(),
        }
        if tool_specs:
            kwargs["toolConfig"] = {"tools": tool_specs}

        body = self.client.converse(**kwargs)
        return self._parse_converse_tool_response(body)

    def converse_with_tools_stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tool_specs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """스트리밍 버전. 텍스트 청크는 stream_handler로 전달된다."""
        stream_handler = get_response_stream_handler()
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
            "inferenceConfig": self._inference_config(),
            **self._guardrail_kwargs(),
        }
        if tool_specs:
            kwargs["toolConfig"] = {"tools": tool_specs}

        response = self.client.converse_stream(**kwargs)

        # 스트림에서 content blocks를 조립
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        current_tool_use: dict[str, Any] | None = None
        current_tool_input_json = ""
        stop_reason = "end_turn"

        for chunk in response["stream"]:
            # 텍스트 델타
            delta = chunk.get("contentBlockDelta")
            if isinstance(delta, dict):
                payload = delta.get("delta", {})
                text = payload.get("text")
                if isinstance(text, str) and text:
                    text_parts.append(text)
                    if stream_handler is not None:
                        stream_handler(text)
                tool_input = payload.get("toolUse", {}).get("input")
                if isinstance(tool_input, str):
                    current_tool_input_json += tool_input

            # content block 시작
            start = chunk.get("contentBlockStart")
            if isinstance(start, dict):
                tool_use_start = start.get("start", {}).get("toolUse")
                if isinstance(tool_use_start, dict):
                    current_tool_use = {
                        "tool_use_id": tool_use_start.get("toolUseId", ""),
                        "name": tool_use_start.get("name", ""),
                    }
                    current_tool_input_json = ""

            # content block 종료
            stop = chunk.get("contentBlockStop")
            if isinstance(stop, dict) and current_tool_use is not None:
                parsed_input = {}
                if current_tool_input_json:
                    try:
                        parsed_input = json.loads(current_tool_input_json)
                    except (json.JSONDecodeError, TypeError):
                        parsed_input = {}
                tool_calls.append({**current_tool_use, "input": parsed_input})
                current_tool_use = None
                current_tool_input_json = ""

            # 메시지 종료
            message_stop = chunk.get("messageStop")
            if isinstance(message_stop, dict):
                stop_reason = message_stop.get("stopReason", "end_turn")

        # assistant 메시지 조립
        content_blocks: list[dict[str, Any]] = []
        combined_text = "".join(text_parts).strip()
        if combined_text:
            content_blocks.append({"text": combined_text})
        for tc in tool_calls:
            content_blocks.append({
                "toolUse": {
                    "toolUseId": tc["tool_use_id"],
                    "name": tc["name"],
                    "input": tc["input"],
                }
            })

        return {
            "stop_reason": stop_reason,
            "assistant_message": {
                "role": "assistant",
                "content": content_blocks,
            },
            "tool_calls": tool_calls,
            "text_content": combined_text or None,
        }

    def _parse_converse_tool_response(self, body: dict[str, Any]) -> dict[str, Any]:
        """Bedrock Converse 응답에서 tool_use와 텍스트를 추출한다."""
        output = body.get("output", {})
        message = output.get("message", {})
        content = message.get("content", [])
        stop_reason = body.get("stopReason", "end_turn")

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                continue
            if "text" in block:
                text_parts.append(str(block["text"]))
            tool_use = block.get("toolUse")
            if isinstance(tool_use, dict):
                tool_calls.append({
                    "tool_use_id": str(tool_use.get("toolUseId", "")),
                    "name": str(tool_use.get("name", "")),
                    "input": tool_use.get("input", {}),
                })

        combined_text = "\n".join(text_parts).strip()
        return {
            "stop_reason": stop_reason,
            "assistant_message": {
                "role": "assistant",
                "content": content,
            },
            "tool_calls": tool_calls,
            "text_content": combined_text or None,
        }

    def _model_text_response(self, *, system_prompt: str, user_prompt: str) -> str:
        if get_response_stream_handler() is not None:
            return self._streaming_text_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        return self._text_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def _text_response(self, *, system_prompt: str, user_prompt: str) -> str:
        body = self.client.converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig=self._inference_config(),
            **self._guardrail_kwargs(),
        )
        return self._extract_text(body).strip()

    def _streaming_text_response(self, *, system_prompt: str, user_prompt: str) -> str:
        stream_handler = get_response_stream_handler()
        response = self.client.converse_stream(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig=self._inference_config(),
            **self._guardrail_kwargs(),
        )
        parts: list[str] = []
        for chunk in response["stream"]:
            delta = chunk.get("contentBlockDelta")
            if not isinstance(delta, dict):
                continue
            payload = delta.get("delta")
            if not isinstance(payload, dict):
                continue
            text = payload.get("text")
            if not isinstance(text, str) or not text:
                continue
            parts.append(text)
            if stream_handler is not None:
                stream_handler(text)
        return "".join(parts).strip()

    def _extract_text(self, body: dict[str, Any]) -> str:
        output = body.get("output")
        if not isinstance(output, dict):
            raise ValueError("missing output in bedrock response")
        message = output.get("message")
        if not isinstance(message, dict):
            raise ValueError("missing message in bedrock response")
        content = message.get("content")
        if not isinstance(content, list):
            raise ValueError("missing content in bedrock response")
        texts = [
            item.get("text")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if not texts:
            raise ValueError("missing text content in bedrock response")
        return "".join(texts)

    def _inference_config(self) -> dict[str, Any]:
        return {
            "maxTokens": self.max_tokens,
            "temperature": 0,
        }

    def _detect_keyword_signal(self, normalized: str) -> tuple[str, str] | None:
        """키워드 패턴 기반 분류 신호를 반환한다. (type, strength: 'strong'|'weak')

        복합 패턴(액션+inquiry)을 먼저 체크해 우선순위를 보장한다.
        """
        # 1. 복합 패턴 우선 — 가장 강한 신호
        for pattern in _INQUIRY_ACTION_PATTERNS:
            if pattern.search(normalized):
                return ("inquiry", "strong")

        # 2. 개별 키워드 카운팅
        inquiry_count = sum(1 for m in INQUIRY_MARKERS if m in normalized)
        command_count = sum(1 for m in COMMAND_MARKERS if m in normalized)
        query_count = sum(1 for m in QUERY_MARKERS if m in normalized)

        nonzero = {
            k: v for k, v in {
                "inquiry": inquiry_count,
                "command": command_count,
                "query": query_count,
            }.items() if v > 0
        }

        if not nonzero:
            return None

        # 단일 카테고리만 매칭 → strong
        if len(nonzero) == 1:
            return (next(iter(nonzero)), "strong")

        # 복수 카테고리 → 최다 카운트로 weak
        dominant = max(nonzero, key=lambda k: nonzero[k])
        return (dominant, "weak")

    def _apply_classification_guardrails(
        self,
        message_text: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        confidence = float(result.get("classification_confidence", 0.0))

        # LLM 신뢰도가 높으면 가드레일 스킵 — LLM 판단을 신뢰
        if confidence >= _GUARDRAIL_SKIP_CONFIDENCE:
            return result

        normalized = message_text.lower()
        signal = self._detect_keyword_signal(normalized)

        # 키워드 신호 없음 → 가드레일 불개입
        if signal is None:
            return result

        signal_type, signal_strength = signal

        # LLM과 키워드 방향이 같으면 신뢰도만 소폭 보강
        if signal_type == result["request_type"]:
            return {
                **result,
                "classification_confidence": max(confidence, 0.80),
            }

        # 키워드가 약한 신호(weak)이거나 LLM 신뢰도가 어느 정도 있으면 불개입
        if signal_strength == "weak" or confidence >= _GUARDRAIL_OVERRIDE_CONFIDENCE:
            return result

        # 강한 키워드 신호 + LLM 신뢰도 낮음 → 보정
        intent_map = {
            "inquiry": "answer_inquiry",
            "command": "execute_command",
            "query": "query_status",
        }
        return {
            "request_type": signal_type,
            "intent": intent_map.get(signal_type, ""),
            "classification_reason": (
                f"가드레일 보정: {signal_type} (LLM confidence={confidence:.2f}, signal={signal_strength})"
            ),
            "classification_confidence": 0.75,
            "operation_candidates": list(result.get("operation_candidates", [])),
            "is_ambiguous": bool(result.get("is_ambiguous", False)),
            "missing_slots": list(result.get("missing_slots", [])),
            "needs_confirmation": signal_type == "command",
        }

    def _fallback_classification(self, message_text: str) -> dict[str, Any]:
        normalized = message_text.lower()

        # 복합 패턴 우선 체크
        signal = self._detect_keyword_signal(normalized)
        if signal is not None:
            signal_type, _ = signal
        elif any(marker in normalized for marker in COMMAND_MARKERS):
            signal_type = "command"
        elif any(marker in normalized for marker in QUERY_MARKERS):
            signal_type = "query"
        else:
            signal_type = "query"

        intent_map = {
            "inquiry": "answer_inquiry",
            "command": "execute_command",
            "query": "query_status",
        }
        return {
            "request_type": signal_type,
            "intent": intent_map.get(signal_type, "query_status"),
            "classification_reason": "LLM fallback 분류",
            "classification_confidence": 0.7,
            "operation_candidates": [],
            "is_ambiguous": False,
            "missing_slots": [],
            "needs_confirmation": signal_type == "command",
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

    def _fallback_plan_object(
        self,
        *,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, Any]:
        operation_id = candidate_operation_ids[0] if candidate_operation_ids else f"{request_type}.unknown"
        specialist = operation_id.split(".", 1)[0]
        return {
            "goal": message_text,
            "specialist": specialist,
            "entities": {},
            "constraints": {"approval_required": request_type == "command"},
            "candidate_steps": [
                {
                    "step_id": "primary-operation",
                    "title": "주요 작업 실행",
                    "status": "planned",
                    "operation_id": operation_id,
                }
            ],
            "risk_level": "medium" if request_type == "command" else "low",
            "required_clarifications": [],
        }

    def _fallback_verifier_decision(self, execution_result: dict[str, Any]) -> dict[str, Any]:
        status_code = int(execution_result.get("status_code", 200))
        if execution_result.get("success") is False:
            if status_code >= 500:
                return {
                    "decision": "retry",
                    "summary": str(execution_result.get("summary", "일시적 오류가 발생했습니다.")),
                    "missing_inputs": [],
                    "follow_up_action": "retry",
                }
            if status_code in {400, 404, 409, 422}:
                return {
                    "decision": "clarify",
                    "summary": str(execution_result.get("summary", "추가 입력이 필요합니다.")),
                    "missing_inputs": [],
                    "follow_up_action": "fill_inputs",
                }
            if status_code in {401, 403}:
                return {
                    "decision": "escalate",
                    "summary": str(execution_result.get("summary", "권한 확인이 필요합니다.")),
                    "missing_inputs": [],
                    "follow_up_action": "human_review",
                }
            return {
                "decision": "stop",
                "summary": str(execution_result.get("summary", "요청을 종료합니다.")),
                "missing_inputs": [],
                "follow_up_action": "stop",
            }
        return {
            "decision": "success",
            "summary": str(execution_result.get("summary", "실행 결과를 확인했습니다.")),
            "missing_inputs": [],
            "follow_up_action": "complete",
        }

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
