from __future__ import annotations

import json

from chatops.services.llm import BedrockLLMService
from chatops.services.response_streaming import response_stream_handler_context

MODEL_ID = "amazon.nova-2-lite-v1:0"


class FakeBedrockRuntimeClient:
    def __init__(
        self,
        *,
        converse_response: dict[str, object] | None = None,
        stream_chunks: list[dict[str, object]] | None = None,
        converse_error: Exception | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.converse_response = converse_response
        self.stream_chunks = stream_chunks or []
        self.converse_error = converse_error
        self.stream_error = stream_error
        self.converse_calls: list[dict[str, object]] = []
        self.converse_stream_calls: list[dict[str, object]] = []

    def converse(self, **kwargs):
        self.converse_calls.append(kwargs)
        if self.converse_error is not None:
            raise self.converse_error
        return self.converse_response

    def converse_stream(self, **kwargs):
        self.converse_stream_calls.append(kwargs)
        if self.stream_error is not None:
            raise self.stream_error
        return {"stream": iter(self.stream_chunks)}


def _text_response(text: str) -> dict[str, object]:
    return {
        "output": {
            "message": {
                "content": [
                    {"text": text},
                ]
            }
        }
    }


def test_bedrock_llm_service_classifies_message() -> None:
    client = FakeBedrockRuntimeClient(
        converse_response=_text_response(
            json.dumps(
                {
                    "request_type": "command",
                    "intent": "execute_command",
                    "classification_reason": "실행 요청",
                    "classification_confidence": 0.97,
                    "operation_candidates": ["project.create"],
                    "is_ambiguous": False,
                    "missing_slots": [],
                    "needs_confirmation": True,
                }
            )
        )
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.classify("프로젝트 생성해줘")

    assert result["request_type"] == "command"
    assert result["classification_reason"] == "실행 요청"
    assert result["operation_candidates"] == ["project.create"]
    assert result["needs_confirmation"] is True
    assert client.converse_calls[0]["modelId"] == MODEL_ID
    assert client.converse_calls[0]["inferenceConfig"]["temperature"] == 0


def test_bedrock_llm_service_generates_plain_text() -> None:
    client = FakeBedrockRuntimeClient(
        converse_response=_text_response("문의 응답 텍스트"),
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.answer_inquiry("프로젝트 생성 방법 알려줘")

    assert result == "문의 응답 텍스트"
    assert client.converse_calls[0]["messages"][0]["content"][0]["text"].startswith("사용자 문의:")


def test_bedrock_llm_service_streams_inquiry_response_chunks() -> None:
    client = FakeBedrockRuntimeClient(
        stream_chunks=[
            {"contentBlockDelta": {"delta": {"text": "문의 "}}},
            {"contentBlockDelta": {"delta": {"text": "응답"}}},
        ],
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )
    collected: list[str] = []

    with response_stream_handler_context(collected.append):
        result = service.answer_inquiry("프로젝트 생성 방법 알려줘")

    assert result == "문의 응답"
    assert collected == ["문의 ", "응답"]
    assert client.converse_stream_calls[0]["modelId"] == MODEL_ID


def test_bedrock_llm_service_applies_query_guardrail_when_llm_misclassifies() -> None:
    client = FakeBedrockRuntimeClient(
        converse_response=_text_response(
            json.dumps(
                {
                    "request_type": "command",
                    "intent": "execute_command",
                    "classification_reason": "실행 요청",
                    "classification_confidence": 0.61,
                }
            )
        )
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.classify("프로젝트 목록 보여줘")

    assert result["request_type"] == "query"
    assert result["intent"] == "query_status"


def test_bedrock_llm_service_applies_inquiry_guardrail_for_how_to_questions() -> None:
    client = FakeBedrockRuntimeClient(
        converse_response=_text_response(
            json.dumps(
                {
                    "request_type": "command",
                    "intent": "execute_command",
                    "classification_reason": "실행 요청",
                    "classification_confidence": 0.71,
                }
            )
        )
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.classify("프로젝트 생성 방법 알려줘")

    assert result["request_type"] == "inquiry"
    assert result["intent"] == "answer_inquiry"


def test_bedrock_llm_service_falls_back_on_error_for_classification() -> None:
    client = FakeBedrockRuntimeClient(converse_error=RuntimeError("rate limit"))
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.classify("demo 프로젝트 멤버 목록 보여줘")

    assert result["request_type"] == "query"
    assert result["intent"] == "query_status"
    assert "fallback" in result["classification_reason"].lower()


def test_bedrock_llm_service_falls_back_on_error_for_query_interpretation() -> None:
    client = FakeBedrockRuntimeClient(converse_error=RuntimeError("rate limit"))
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.interpret_query_result(
        "demo 프로젝트 멤버 목록 보여줘",
        {"summary": "demo 프로젝트 멤버 목록:\n- alice(OWNER)"},
    )

    assert result == "demo 프로젝트 멤버 목록:\n- alice(OWNER)"


def test_bedrock_llm_service_hides_internal_operation_ids_in_query_fallback() -> None:
    client = FakeBedrockRuntimeClient(converse_error=RuntimeError("rate limit"))
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.interpret_query_result(
        "api-server 트래픽 보여줘",
        {"summary": "monitoring.get_app_deployment_traffic"},
    )

    assert result == "조회 결과를 확인했습니다."


def test_bedrock_llm_service_rejects_unsupported_inquiry_without_model_call() -> None:
    client = FakeBedrockRuntimeClient(
        converse_response=_text_response("호출되면 안 됩니다."),
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.answer_inquiry("프로젝트 백업 방법 알려줘", supported_operations=[])

    assert "지원하지 않는 기능" in result
    assert client.converse_calls == []
    assert client.converse_stream_calls == []


def test_bedrock_llm_service_grounds_inquiry_fallback_on_registry_context() -> None:
    client = FakeBedrockRuntimeClient(converse_error=RuntimeError("rate limit"))
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.answer_inquiry(
        "프로젝트 생성 방법 알려줘",
        supported_operations=[
            {
                "id": "project.create",
                "capability": "프로젝트 생성",
                "requires_confirmation": True,
                "important_inputs": ["프로젝트 이름", "최대 CPU", "최대 메모리", "최대 디스크"],
            }
        ],
    )

    assert "프로젝트 생성" in result
    assert "프로젝트 이름" in result
    assert "승인" in result


def test_bedrock_llm_service_builds_plan_object() -> None:
    client = FakeBedrockRuntimeClient(
        converse_response=_text_response(
            json.dumps(
                {
                    "goal": "demo 프로젝트에 api 앱 생성",
                    "specialist": "application",
                    "entities": {"project_name": "demo", "application_name": "api"},
                    "constraints": {"approval_required": True},
                    "candidate_steps": [
                        {
                            "step_id": "create-app",
                            "title": "앱 생성",
                            "status": "planned",
                            "operation_id": "application.create_apps",
                        }
                    ],
                    "risk_level": "medium",
                    "required_clarifications": ["cpu", "memory", "disk"],
                }
            )
        )
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.build_plan_object(
        message_text="demo 프로젝트에 api 앱 만들어줘",
        request_type="command",
        candidate_operation_ids=["application.create_apps"],
    )

    assert result["specialist"] == "application"
    assert result["candidate_steps"][0]["operation_id"] == "application.create_apps"


def test_bedrock_llm_service_verifies_execution_result() -> None:
    client = FakeBedrockRuntimeClient(
        converse_response=_text_response(
            json.dumps(
                {
                    "decision": "success",
                    "summary": "검증 결과 문제가 없습니다.",
                    "missing_inputs": [],
                    "follow_up_action": "complete",
                }
            )
        )
    )
    service = BedrockLLMService(
        model_id=MODEL_ID,
        timeout_seconds=10,
        client=client,
    )

    result = service.verify_execution(
        execution_result={"success": True, "summary": "앱 생성 완료", "status_code": 200},
    )

    assert result["decision"] == "success"
    assert result["follow_up_action"] == "complete"
