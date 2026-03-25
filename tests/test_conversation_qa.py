"""대화 QA 세트: 실제 사용자 시나리오 기반의 end-to-end 대화 흐름 검증.

설계 문서(2026-03-25-conversational-ux-100-percent-design.md) 기준으로
자주 쓰는 자연어 패턴, 축약어, 정정, 취소, 재승인, 연속 요청을 검증한다.
"""

from __future__ import annotations

from chatops.graph.service import GraphService
from chatops.services.resolver import ParameterResolverService

from tests.test_graph_service import (
    FakeDownstreamDispatcher,
    FakeLLMService,
    FakeRegistryService,
    FakeResolverService,
)


def _make_graph_service(
    dispatcher=None,
    registry=None,
    resolver=None,
) -> GraphService:
    return GraphService(
        llm_service=FakeLLMService(),
        registry_service=registry or FakeRegistryService(),
        adapter_service=dispatcher or FakeDownstreamDispatcher(),
        resolver_service=resolver or ParameterResolverService(),
    )


# === 시나리오 1: 프로젝트 생성 전체 흐름 (정보 부족 → 보충 → 승인) ===

class TestProjectCreateFlow:
    def test_step1_initial_request_asks_for_missing_values(self) -> None:
        """사용자: '프로젝트 하나 만들어줘' → 부족한 정보 질문"""
        gs = _make_graph_service()
        result = gs.handle_request(
            session_id=1, user_id="u1", message_text="프로젝트 하나 만들어줘",
        )
        assert result.status == "input_required"
        assert "프로젝트 이름" in result.final_response
        assert "최대 CPU" in result.final_response

    def test_step2_provide_all_values_gets_plan(self) -> None:
        """사용자: '이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야' → 실행 계획"""
        gs = _make_graph_service()
        result = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
            session_context={
                "last_message_text": "프로젝트 하나 만들어줘",
                "last_request_status": "input_required",
                "last_request_type": "command",
            },
        )
        assert result.status == "pending_approval"
        assert "프로젝트 이름 demo" in result.final_response
        assert "실행할까요" in result.final_response
        assert "project.create" not in result.final_response

    def test_step3_approve_and_complete(self) -> None:
        """사용자: '응' (승인) → 프로젝트 생성 완료"""
        gs = _make_graph_service()
        pending = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )
        assert pending.status == "pending_approval"

        completed = gs.resume_request(
            request_id=pending.request_id,
            session_id=1, user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
            approval_granted=True,
        )
        assert completed.status == "completed"
        assert "생성했습니다" in completed.final_response


# === 시나리오 2: 정정 흐름 ===

class TestCorrectionFlow:
    def test_correct_cpu_during_plan(self) -> None:
        """사용자가 승인 대기 중 'CPU는 2로 해줘'로 정정"""
        gs = _make_graph_service()
        first = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
            session_context={
                "last_message_text": "프로젝트 하나 만들어줘",
                "last_request_status": "input_required",
                "last_request_type": "command",
            },
        )
        assert first.status == "pending_approval"

        second = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="아니 cpu는 2로 바꿔줘",
            session_context={
                "last_message_text": "이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
                "last_effective_message_text": first.effective_message_text,
                "last_request_status": "pending_approval",
                "last_request_type": "command",
            },
        )
        assert second.status == "pending_approval"
        assert "최대 CPU 2" in second.final_response
        # 나머지 값은 유지되어야 함
        assert "프로젝트 이름 demo" in second.final_response
        assert "최대 메모리 0.5GB" in second.final_response

    def test_correct_name_during_plan(self) -> None:
        """프로젝트 이름을 정정하면 새 이름으로 계획이 바뀜"""
        gs = _make_graph_service()
        first = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="이름은 old야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
            session_context={
                "last_message_text": "프로젝트 하나 만들어줘",
                "last_request_status": "input_required",
                "last_request_type": "command",
            },
        )
        second = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="아니 이름은 newproj로 바꿔줘",
            session_context={
                "last_message_text": "이름은 old야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
                "last_effective_message_text": first.effective_message_text,
                "last_request_status": "pending_approval",
                "last_request_type": "command",
            },
        )
        assert second.status == "pending_approval"
        assert "프로젝트 이름 newproj" in second.final_response


# === 시나리오 3: 거절 후 새 요청 ===

class TestRejectionFlow:
    def test_reject_then_new_request(self) -> None:
        """승인 거절 후 새 명령을 바로 시작할 수 있음"""
        gs = _make_graph_service()
        pending = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )
        rejected = gs.resume_request(
            request_id=pending.request_id,
            session_id=1, user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
            approval_granted=False,
        )
        assert rejected.status == "rejected"
        assert "취소했습니다" in rejected.final_response


# === 시나리오 4: 부분값 보충 (2턴에 걸쳐) ===

class TestMultiTurnCollection:
    def test_partial_then_complete(self) -> None:
        """1턴: 이름+CPU만, 2턴: 나머지 → pending_approval"""
        gs = _make_graph_service()
        first = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="이름은 demo야 cpu는 1이야",
            session_context={
                "last_message_text": "프로젝트 하나 만들어줘",
                "last_request_status": "input_required",
                "last_request_type": "command",
            },
        )
        assert first.status == "input_required"
        assert "max_memory" in first.missing_inputs
        assert "max_disk" in first.missing_inputs

        second = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="메모리는 0.5야 디스크는 10이야",
            session_context={
                "last_message_text": "이름은 demo야 cpu는 1이야",
                "last_effective_message_text": first.effective_message_text,
                "last_request_status": "input_required",
                "last_request_type": "command",
            },
        )
        assert second.status == "pending_approval"
        assert "프로젝트 이름 demo" in second.final_response
        assert "최대 메모리 0.5GB" in second.final_response


# === 시나리오 5: 내부 ID 미노출 검증 ===

class TestNoInternalIdExposure:
    def test_plan_never_shows_operation_id(self) -> None:
        gs = _make_graph_service()
        result = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )
        assert result.status == "pending_approval"
        assert "project.create" not in result.final_response

    def test_input_required_never_shows_field_names(self) -> None:
        gs = _make_graph_service()
        result = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="프로젝트 하나 만들어줘",
        )
        assert result.status == "input_required"
        # 내부 필드명이 아닌 사용자 표현을 사용해야 함
        assert "max_cpu" not in result.final_response
        assert "max_memory" not in result.final_response
        assert "max_disk" not in result.final_response


# === 시나리오 6: 다양한 구어체 표현 ===

class TestColloquialExpressions:
    def test_key_value_with_korean_postposition(self) -> None:
        """'이름은 demo야 cpu는 1이야' 형식"""
        gs = _make_graph_service()
        result = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="이름은 demo야 cpu는 1이야 메모리는 0.5야 디스크는 10이야",
            session_context={
                "last_message_text": "프로젝트 하나 만들어줘",
                "last_request_status": "input_required",
                "last_request_type": "command",
            },
        )
        assert result.status == "pending_approval"

    def test_key_value_with_equals(self) -> None:
        """'name=demo max_cpu=1' 형식"""
        gs = _make_graph_service()
        result = gs.handle_request(
            session_id=1, user_id="u1",
            message_text="프로젝트 생성 name=demo max_cpu=1 max_memory=0.5 max_disk=10",
        )
        assert result.status == "pending_approval"
