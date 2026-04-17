"""대화 QA 세트: Agent Loop 기반 end-to-end 대화 흐름 검증.

Agent Loop (agent_reasoning → safety_gate → execute_tool)를 사용하여
자연어 패턴, 정정, 취소, 연속 요청을 검증한다.
"""

from __future__ import annotations

from tests.test_agent_loop import (
    FakeAgentLLMService,
    FakeAgentRegistryService,
    FakeAgentDownstreamDispatcher,
    FakeAgentResolverService,
    _COMMAND_ENTRY,
    _QUERY_ENTRY,
    _text_response,
    _tool_use_response,
    _make_agent_service,
)


# === 시나리오 1: 프로젝트 생성 전체 흐름 (정보 부족 → 보충 → 승인) ===

class TestProjectCreateFlow:
    def test_step1_incomplete_request_asks_for_params(self) -> None:
        """'프로젝트 하나 만들어줘' → LLM이 이름/CPU/메모리/디스크를 질문한다."""
        llm = FakeAgentLLMService(responses=[
            _text_response("프로젝트를 생성하려면 이름과 CPU, 메모리, 디스크 정보가 필요합니다."),
        ])
        service = _make_agent_service(llm=llm)

        result = service.handle_request(
            session_id=1001,
            user_id="u1",
            message_text="프로젝트 하나 만들어줘",
        )

        assert result.status == "completed"
        assert result.selected_operation_ids == []
        assert "이름" in result.final_response or "CPU" in result.final_response

    def test_step2_full_params_triggers_approval_interrupt(self) -> None:
        """Turn1(파라미터 부족) + Turn2(모든 파라미터, 동일 session_id) → LLM이 project__create 호출 → interrupt()."""
        dispatcher = FakeAgentDownstreamDispatcher()
        llm = FakeAgentLLMService(responses=[
            # Turn1: 파라미터 부족, 질문 응답
            _text_response("프로젝트 이름과 CPU, 메모리, 디스크 정보를 알려주세요."),
            # Turn2: 파라미터 제공 후 도구 호출 → safety_gate에서 interrupt
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        # Turn 1: 파라미터 없이 요청
        service.handle_request(
            session_id=1002,
            user_id="u1",
            message_text="프로젝트 하나 만들어줘",
        )

        # Turn 2: 파라미터 제공 (동일 session_id)
        result = service.handle_request(
            session_id=1002,
            user_id="u1",
            message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
        )

        # interrupt()가 발생했으므로 dispatcher는 아직 호출되지 않아야 함
        assert len(dispatcher.executed_operation_ids) == 0

    def test_step3_approval_executes_and_completes(self) -> None:
        """Turn1 + Turn2 + resume_request(approval_granted=True) → dispatcher 호출 → status='completed', '생성' 포함."""
        dispatcher = FakeAgentDownstreamDispatcher(
            execute_result={"summary": "프로젝트 생성 완료", "success": True},
        )
        llm = FakeAgentLLMService(responses=[
            # Turn1: 질문 응답
            _text_response("프로젝트 이름과 CPU, 메모리, 디스크 정보를 알려주세요."),
            # Turn2: 도구 호출 (→ interrupt)
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
            # resume 후: 실행 결과 받아 최종 응답
            _text_response("demo 프로젝트를 생성했습니다."),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        # Turn 1
        service.handle_request(
            session_id=1003,
            user_id="u1",
            message_text="프로젝트 하나 만들어줘",
        )

        # Turn 2: 파라미터 제공 → interrupt
        pending = service.handle_request(
            session_id=1003,
            user_id="u1",
            message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
        )

        # 승인
        completed = service.resume_request(
            request_id=pending.request_id,
            session_id=1003,
            user_id="u1",
            message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
            approval_granted=True,
        )

        assert completed.status == "completed"
        assert "생성" in completed.final_response


# === 시나리오 2: 정정 흐름 ===

class TestCorrectionFlow:
    def test_correct_param_after_rejection_executes_with_new_value(self) -> None:
        """거절 후 새 요청에서 정정된 값으로 재실행된다.

        Scenario:
        - handle_request → tool_use(max_cpu=1) → interrupted
        - resume(rejected) → safety_gate returns error → agent_reasoning says '취소했습니다' → completed
        - new handle_request(correction 'cpu는 2로') → tool_use(max_cpu=2) → interrupted
        - resume(approved) → completed
        """
        dispatcher = FakeAgentDownstreamDispatcher(
            execute_result={"summary": "cpu 2로 프로젝트 생성 완료", "success": True},
        )
        llm = FakeAgentLLMService(responses=[
            # 1차 요청: tool_use(cpu=1)
            _tool_use_response("project__create", {"name": "demo", "max_cpu": 1, "max_memory": 0.5, "max_disk": 10}),
            # 거절 후: LLM이 취소 메시지 생성
            _text_response("요청을 취소했습니다."),
            # 2차 요청(정정): tool_use(cpu=2)
            _tool_use_response("project__create", {"name": "demo", "max_cpu": 2, "max_memory": 0.5, "max_disk": 10}),
            # 승인 후: 완료 메시지
            _text_response("cpu 2로 프로젝트를 생성했습니다."),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        # 1차 요청 → interrupt
        pending1 = service.handle_request(
            session_id=2001,
            user_id="u1",
            message_text="프로젝트 만들어줘 cpu는 1이야",
        )

        # 거절
        service.resume_request(
            request_id=pending1.request_id,
            session_id=2001,
            user_id="u1",
            message_text="프로젝트 만들어줘 cpu는 1이야",
            approval_granted=False,
        )

        # 정정 요청 → interrupt
        pending2 = service.handle_request(
            session_id=2001,
            user_id="u1",
            message_text="cpu는 2로 바꿔서 만들어줘",
        )

        # 승인
        completed = service.resume_request(
            request_id=pending2.request_id,
            session_id=2001,
            user_id="u1",
            message_text="cpu는 2로 바꿔서 만들어줘",
            approval_granted=True,
        )

        assert len(dispatcher.executed_operation_ids) == 1
        assert completed.status == "completed"

    def test_correction_uses_session_context(self) -> None:
        """거절 후 새 요청에서 LLM이 받는 messages에 이전 대화 내용이 포함된다."""
        dispatcher = FakeAgentDownstreamDispatcher(
            execute_result={"summary": "완료", "success": True},
        )
        llm = FakeAgentLLMService(responses=[
            # 1차: tool_use → interrupt
            _tool_use_response("project__create", {"name": "demo", "max_cpu": 1, "max_memory": 0.5, "max_disk": 10}),
            # 거절 후: 취소 메시지
            _text_response("취소했습니다."),
            # 2차: 정정 요청 → tool_use
            _tool_use_response("project__create", {"name": "demo", "max_cpu": 2, "max_memory": 0.5, "max_disk": 10}),
            # 승인 후: 완료
            _text_response("완료했습니다."),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        # 1차 요청 → interrupt
        pending1 = service.handle_request(
            session_id=2002,
            user_id="u1",
            message_text="프로젝트 만들어줘 cpu는 1이야",
        )
        # 거절
        service.resume_request(
            request_id=pending1.request_id,
            session_id=2002,
            user_id="u1",
            message_text="프로젝트 만들어줘 cpu는 1이야",
            approval_granted=False,
        )
        # 2차 요청 (정정)
        pending2 = service.handle_request(
            session_id=2002,
            user_id="u1",
            message_text="cpu는 2로 바꿔줘",
        )
        # 승인
        service.resume_request(
            request_id=pending2.request_id,
            session_id=2002,
            user_id="u1",
            message_text="cpu는 2로 바꿔줘",
            approval_granted=True,
        )

        # 2차 요청의 agent_reasoning 호출 시 이전 대화 맥락이 포함되어야 함
        # recorded_messages[2]는 거절 후 새 handle_request에서의 호출
        # 이전 대화(user, assistant tool_use, user tool_result, assistant 취소) + 새 user = 최소 5개
        assert len(llm.recorded_messages) >= 3
        assert len(llm.recorded_messages[2]) >= 5


# === 시나리오 3: 거절 후 새 요청 ===

class TestRejectionFlow:
    def test_reject_stops_execution(self) -> None:
        """승인 거절 시 dispatcher가 호출되지 않고, '취소' 메시지가 포함된다."""
        dispatcher = FakeAgentDownstreamDispatcher()
        llm = FakeAgentLLMService(responses=[
            # 도구 호출 → interrupt
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
            # 거절 후: LLM이 취소 설명
            _text_response("요청을 취소했습니다."),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        # 요청 → interrupt
        pending = service.handle_request(
            session_id=3001,
            user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )

        # 거절
        result = service.resume_request(
            request_id=pending.request_id,
            session_id=3001,
            user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
            approval_granted=False,
        )

        assert len(dispatcher.executed_operation_ids) == 0
        assert "취소" in result.final_response
        assert result.status == "completed"


# === 시나리오 4: 부분값 보충 (2턴에 걸쳐) ===

class TestMultiTurnCollection:
    def test_partial_params_then_complete_params_executes(self) -> None:
        """Turn1: 일부 파라미터 → 질문. Turn2: 나머지 파라미터 → tool_use → interrupt. Turn3: 승인 → 완료."""
        dispatcher = FakeAgentDownstreamDispatcher(
            execute_result={"summary": "demo 프로젝트 생성 완료", "success": True},
        )
        llm = FakeAgentLLMService(responses=[
            # Turn1: 이름+CPU만, 나머지 질문
            _text_response("메모리와 디스크 정보도 알려주세요."),
            # Turn2: 나머지 파라미터 제공 → 도구 호출
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
            # Turn3: resume 후 완료 응답
            _text_response("demo 프로젝트를 생성했습니다."),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        # Turn 1: 일부 파라미터
        turn1 = service.handle_request(
            session_id=4001,
            user_id="u1",
            message_text="이름은 demo야 cpu는 1이야",
        )
        assert turn1.status == "completed"
        assert turn1.selected_operation_ids == []

        # Turn 2: 나머지 파라미터 → interrupt
        pending = service.handle_request(
            session_id=4001,
            user_id="u1",
            message_text="메모리는 0.5야 디스크는 10이야",
        )

        # Turn 3: 승인
        completed = service.resume_request(
            request_id=pending.request_id,
            session_id=4001,
            user_id="u1",
            message_text="메모리는 0.5야 디스크는 10이야",
            approval_granted=True,
        )

        assert dispatcher.last_operation_id == "project.create"
        assert completed.status == "completed"


# === 시나리오 5: 내부 ID 미노출 검증 ===

class TestNoInternalIdExposure:
    def test_final_response_does_not_contain_operation_id(self) -> None:
        """LLM이 사용자 친화적 텍스트로 응답 → 최종 응답에 'project.create'가 없어야 한다."""
        llm = FakeAgentLLMService(responses=[
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
            _text_response("demo 프로젝트를 성공적으로 생성했습니다."),
        ])
        dispatcher = FakeAgentDownstreamDispatcher(
            execute_result={"summary": "생성 완료", "success": True},
        )
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        pending = service.handle_request(
            session_id=5001,
            user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )
        result = service.resume_request(
            request_id=pending.request_id,
            session_id=5001,
            user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
            approval_granted=True,
        )

        assert "project.create" not in result.final_response

    def test_final_response_does_not_contain_internal_field_names(self) -> None:
        """LLM 응답에 max_cpu/max_memory 등 내부 필드명이 포함되지 않아야 한다."""
        llm = FakeAgentLLMService(responses=[
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
            _text_response("demo 프로젝트를 CPU 1코어, 메모리 0.5GB, 디스크 10GB로 생성했습니다."),
        ])
        dispatcher = FakeAgentDownstreamDispatcher(
            execute_result={"summary": "생성 완료", "success": True},
        )
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        pending = service.handle_request(
            session_id=5002,
            user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )
        result = service.resume_request(
            request_id=pending.request_id,
            session_id=5002,
            user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
            approval_granted=True,
        )

        assert "max_cpu" not in result.final_response
        assert "max_memory" not in result.final_response


# === 시나리오 6: 다양한 구어체 표현 ===

class TestColloquialExpressions:
    def test_korean_postposition_input(self) -> None:
        """'이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야' 형식 → LLM이 도구 호출 → interrupt."""
        dispatcher = FakeAgentDownstreamDispatcher()
        llm = FakeAgentLLMService(responses=[
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        result = service.handle_request(
            session_id=6001,
            user_id="u1",
            message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
        )

        # interrupt()가 발생하여 dispatcher는 아직 호출되지 않아야 함
        assert len(dispatcher.executed_operation_ids) == 0

    def test_equals_format_input(self) -> None:
        """'name=demo max_cpu=1 max_memory=0.5 max_disk=10' 형식 → LLM이 도구 호출 → interrupt."""
        dispatcher = FakeAgentDownstreamDispatcher()
        llm = FakeAgentLLMService(responses=[
            _tool_use_response("project__create", {
                "name": "demo",
                "max_cpu": 1,
                "max_memory": 0.5,
                "max_disk": 10,
            }),
        ])
        service = _make_agent_service(llm=llm, dispatcher=dispatcher)

        result = service.handle_request(
            session_id=6002,
            user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )

        # interrupt()가 발생하여 dispatcher는 아직 호출되지 않아야 함
        assert len(dispatcher.executed_operation_ids) == 0
