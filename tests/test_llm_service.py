from __future__ import annotations

import json

import httpx

from chatops.services.llm import GroqLLMService


def test_groq_llm_service_classifies_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.groq.com/openai/v1/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "llama-3.3-70b-versatile"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "request_type": "command",
                                    "intent": "execute_command",
                                    "classification_reason": "실행 요청",
                                    "classification_confidence": 0.97,
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = GroqLLMService(
        api_key="test-key",
        model="llama-3.3-70b-versatile",
        timeout_seconds=10,
        client=client,
    )

    result = service.classify("프로젝트 생성해줘")

    assert result["request_type"] == "command"
    assert result["classification_reason"] == "실행 요청"


def test_groq_llm_service_generates_plain_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert "response_format" not in payload
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "문의 응답 텍스트"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = GroqLLMService(
        api_key="test-key",
        model="llama-3.3-70b-versatile",
        timeout_seconds=10,
        client=client,
    )

    result = service.answer_inquiry("프로젝트 생성 방법 알려줘")

    assert result == "문의 응답 텍스트"
