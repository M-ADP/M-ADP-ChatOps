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
                                    "operation_candidates": ["project.create"],
                                    "is_ambiguous": False,
                                    "missing_slots": [],
                                    "needs_confirmation": True,
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
    assert result["operation_candidates"] == ["project.create"]
    assert result["needs_confirmation"] is True


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


def test_groq_llm_service_applies_query_guardrail_when_llm_misclassifies() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
                                    "classification_confidence": 0.61,
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

    result = service.classify("프로젝트 목록 보여줘")

    assert result["request_type"] == "query"
    assert result["intent"] == "query_status"


def test_groq_llm_service_applies_inquiry_guardrail_for_how_to_questions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
                                    "classification_confidence": 0.71,
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

    result = service.classify("프로젝트 생성 방법 알려줘")

    assert result["request_type"] == "inquiry"
    assert result["intent"] == "answer_inquiry"


def test_groq_llm_service_falls_back_on_rate_limit_for_classification() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = GroqLLMService(
        api_key="test-key",
        model="llama-3.3-70b-versatile",
        timeout_seconds=10,
        client=client,
    )

    result = service.classify("demo 프로젝트 멤버 목록 보여줘")

    assert result["request_type"] == "query"
    assert result["intent"] == "query_status"
    assert "fallback" in result["classification_reason"].lower()


def test_groq_llm_service_falls_back_on_rate_limit_for_query_interpretation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = GroqLLMService(
        api_key="test-key",
        model="llama-3.3-70b-versatile",
        timeout_seconds=10,
        client=client,
    )

    result = service.interpret_query_result(
        "demo 프로젝트 멤버 목록 보여줘",
        {"summary": "demo 프로젝트 멤버 목록:\n- alice(OWNER)"},
    )

    assert result == "demo 프로젝트 멤버 목록:\n- alice(OWNER)"


def test_groq_llm_service_hides_internal_operation_ids_in_query_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = GroqLLMService(
        api_key="test-key",
        model="llama-3.3-70b-versatile",
        timeout_seconds=10,
        client=client,
    )

    result = service.interpret_query_result(
        "api-server 트래픽 보여줘",
        {"summary": "monitoring.get_app_deployment_traffic"},
    )

    assert result == "조회 결과를 확인했습니다."


def test_groq_llm_service_rejects_unsupported_inquiry_without_llm_call() -> None:
    service = GroqLLMService(
        api_key="test-key",
        model="llama-3.3-70b-versatile",
        timeout_seconds=10,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    result = service.answer_inquiry("프로젝트 백업 방법 알려줘", supported_operations=[])

    assert "지원하지 않는 기능" in result


def test_groq_llm_service_grounds_inquiry_fallback_on_registry_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = GroqLLMService(
        api_key="test-key",
        model="llama-3.3-70b-versatile",
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


def test_groq_llm_service_builds_plan_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
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

    result = service.build_plan_object(
        message_text="demo 프로젝트에 api 앱 만들어줘",
        request_type="command",
        candidate_operation_ids=["application.create_apps"],
    )

    assert result["specialist"] == "application"
    assert result["candidate_steps"][0]["operation_id"] == "application.create_apps"


def test_groq_llm_service_verifies_execution_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "decision": "success",
                                    "summary": "검증 결과 문제가 없습니다.",
                                    "missing_inputs": [],
                                    "follow_up_action": "complete",
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

    result = service.verify_execution(
        execution_result={"success": True, "summary": "앱 생성 완료", "status_code": 200},
    )

    assert result["decision"] == "success"
    assert result["follow_up_action"] == "complete"
