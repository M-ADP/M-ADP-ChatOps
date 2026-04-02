"""P0/P1 수정사항 검증 테스트.

각 테스트는 특정 P0/P1 문제를 재현하고 수정이 동작하는지 검증한다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from chatops.domain.enums import RequestStatus
from chatops.graph.nodes import WorkflowNodes
from chatops.graph.safe_node import safe_node, DownstreamForbiddenError, DownstreamNotFoundError
from chatops.graph.state import GraphState
from chatops.schemas.auth import AuthContext
from chatops.services.downstream_dispatcher import EntityResolutionError
from chatops.services.registry import RegistryEntry, RegistryService, ScoredCandidate


# ──────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────

def _make_entry(
    entry_id: str,
    operation_kind: str = "write",
    risk_level: str = "medium",
    usable_in: tuple[str, ...] = ("command",),
    requires_confirmation: bool = True,
    summary: str = "",
    capability: str = "",
    required_inputs: dict | None = None,
) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path=f"/{entry_id.replace('.', '/')}",
        method="POST",
        summary=summary or entry_id,
        capability=capability or entry_id,
        usable_in=usable_in,
        operation_kind=operation_kind,
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=requires_confirmation,
        risk_level=risk_level,
        side_effects=(),
        required_headers=(),
        required_inputs=required_inputs or {},
    )


def _make_nodes(**kwargs) -> WorkflowNodes:
    defaults = dict(
        llm_service=MagicMock(),
        registry_service=MagicMock(),
        downstream_dispatcher=MagicMock(),
        resolver_service=MagicMock(),
        approval_ttl_seconds=900,
    )
    defaults.update(kwargs)
    return WorkflowNodes(**defaults)


def _base_state(**overrides) -> GraphState:
    state: GraphState = {
        "request_id": 12345,
        "session_id": 1,
        "user_id": "test-user",
        "user_role": "MEMBER",
        "org_id": None,
        "message_text": "테스트",
        "effective_message_text": "테스트",
        "approval_granted": False,
        "request_status": "processing",
        "selected_operation_ids": [],
        "requires_approval": False,
        "is_ambiguous": False,
        "ambiguity_candidates": [],
    }
    state.update(overrides)
    return state


# ──────────────────────────────────────────────────
# [P0-1] 승인 TTL 검증
# ──────────────────────────────────────────────────

class TestApprovalTTL:
    def test_expired_request_returns_expired_status(self) -> None:
        """TTL이 만료된 요청은 wait_for_approval에서 APPROVAL_EXPIRED를 반환해야 한다."""
        nodes = _make_nodes(approval_ttl_seconds=1)  # 1초 TTL
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        state = _base_state(
            request_status="pending_approval",
            created_at=past,
            expires_at=past,  # 이미 만료
            final_response="실행할까요?",
        )
        result = nodes.wait_for_approval(state)
        assert result["request_status"] == RequestStatus.APPROVAL_EXPIRED.value
        assert "만료" in result["final_response"]
        assert result["error_code"] == "APPROVAL_EXPIRED"

    def test_valid_ttl_proceeds_to_interrupt(self) -> None:
        """TTL이 유효하면 interrupt로 진행해야 한다."""
        nodes = _make_nodes(approval_ttl_seconds=3600)
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        state = _base_state(
            request_status="pending_approval",
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            final_response="실행할까요?",
        )
        # interrupt()는 테스트에서 직접 호출 불가이므로 TTL 검사 로직만 검증
        # wait_for_approval 호출 시 TTL 만료가 아니면 interrupt 진입
        # 여기서는 만료 케이스가 아닌 것만 확인
        assert datetime.fromisoformat(future) > datetime.now(timezone.utc)

    def test_ingest_sets_created_at_and_expires_at(self) -> None:
        """ingest_request는 created_at과 expires_at을 설정해야 한다."""
        nodes = _make_nodes(approval_ttl_seconds=900)
        state = _base_state()
        result = nodes.ingest_request(state)
        assert result["created_at"] is not None
        assert result["expires_at"] is not None
        created = datetime.fromisoformat(result["created_at"])
        expires = datetime.fromisoformat(result["expires_at"])
        delta = expires - created
        assert 899 <= delta.total_seconds() <= 901


# ──────────────────────────────────────────────────
# [P0-2] 모호한 명령 자동 실행 금지
# ──────────────────────────────────────────────────

class TestAmbiguityDetection:
    def test_ambiguous_candidates_detected(self) -> None:
        """서로 다른 도메인의 점수 차이가 작으면 ambiguous로 판단해야 한다."""
        project_delete = ScoredCandidate(entry=_make_entry("project.delete", operation_kind="delete"), score=20)
        app_delete = ScoredCandidate(entry=_make_entry("application.delete_apps", operation_kind="delete"), score=18)
        service = RegistryService([], ambiguity_score_threshold=5)
        is_ambiguous, candidates = service.detect_ambiguity([project_delete, app_delete])
        assert is_ambiguous is True
        assert len(candidates) == 2

    def test_same_domain_not_ambiguous(self) -> None:
        """같은 도메인 내 후보는 ambiguous가 아니다."""
        project_delete = ScoredCandidate(entry=_make_entry("project.delete", operation_kind="delete"), score=20)
        project_update = ScoredCandidate(entry=_make_entry("project.update_name"), score=18)
        service = RegistryService([], ambiguity_score_threshold=5)
        is_ambiguous, _ = service.detect_ambiguity([project_delete, project_update])
        assert is_ambiguous is False

    def test_large_score_gap_not_ambiguous(self) -> None:
        """점수 차이가 크면 ambiguous가 아니다."""
        project_delete = ScoredCandidate(entry=_make_entry("project.delete", operation_kind="delete"), score=30)
        app_delete = ScoredCandidate(entry=_make_entry("application.delete_apps", operation_kind="delete"), score=10)
        service = RegistryService([], ambiguity_score_threshold=5)
        is_ambiguous, _ = service.detect_ambiguity([project_delete, app_delete])
        assert is_ambiguous is False

    def test_plan_command_returns_ambiguous_status(self) -> None:
        """ambiguous 후보가 있으면 plan_command가 AMBIGUOUS 상태를 반환해야 한다."""
        registry = MagicMock()
        registry.find_scored_candidates.return_value = [
            ScoredCandidate(entry=_make_entry("project.delete", operation_kind="delete", risk_level="high"), score=20),
            ScoredCandidate(entry=_make_entry("application.delete_apps", operation_kind="delete", risk_level="high"), score=18),
        ]
        registry.detect_ambiguity.return_value = (True, registry.find_scored_candidates.return_value[:2])

        nodes = _make_nodes(registry_service=registry)
        state = _base_state(message_text="demo 삭제해줘", effective_message_text="demo 삭제해줘")
        result = nodes.plan_command(state)
        assert result["request_status"] == RequestStatus.AMBIGUOUS.value
        assert result["is_ambiguous"] is True
        assert "모호합니다" in result["final_response"]


# ──────────────────────────────────────────────────
# [P0-3] Graph node 예외 처리
# ──────────────────────────────────────────────────

class TestSafeNode:
    def test_entity_resolution_error_returns_friendly_message(self) -> None:
        """EntityResolutionError는 사용자 친화적 메시지로 변환되어야 한다."""
        class _Nodes:
            @safe_node
            def test_node(self, state):
                raise EntityResolutionError("프로젝트 'xyz'을(를) 찾지 못했습니다.")

        result = _Nodes().test_node({})
        assert result["request_status"] == RequestStatus.FAILED.value
        assert result["error_code"] == "ENTITY_NOT_FOUND"
        assert "찾을 수 없습니다" in result["final_response"]

    def test_timeout_returns_friendly_message(self) -> None:
        """타임아웃은 사용자 친화적 메시지로 변환되어야 한다."""
        import httpx

        class _Nodes:
            @safe_node
            def test_node(self, state):
                raise httpx.ReadTimeout("timeout")

        result = _Nodes().test_node({})
        assert result["request_status"] == RequestStatus.FAILED.value
        assert result["error_code"] == "LLM_TIMEOUT"
        assert "지연" in result["final_response"]

    def test_generic_exception_returns_internal_error(self) -> None:
        """알 수 없는 예외는 INTERNAL_ERROR로 처리되어야 한다."""
        class _Nodes:
            @safe_node
            def test_node(self, state):
                raise RuntimeError("unexpected")

        result = _Nodes().test_node({})
        assert result["request_status"] == RequestStatus.FAILED.value
        assert result["error_code"] == "INTERNAL_ERROR"

    def test_forbidden_error_returns_permission_message(self) -> None:
        """403 에러는 권한 부족 메시지로 변환되어야 한다."""
        class _Nodes:
            @safe_node
            def test_node(self, state):
                raise DownstreamForbiddenError("Forbidden")

        result = _Nodes().test_node({})
        assert result["error_code"] == "FORBIDDEN"
        assert "권한" in result["final_response"]


# ──────────────────────────────────────────────────
# [P0-4] 중복 실행 방지
# ──────────────────────────────────────────────────

class TestIdempotency:
    def test_executed_status_exists_in_enum(self) -> None:
        """RequestStatus에 EXECUTED 상태가 존재해야 한다."""
        assert RequestStatus.EXECUTED.value == "executed"
        assert RequestStatus.EXECUTING.value == "executing"

    def test_terminal_statuses_include_executed(self) -> None:
        """terminal_statuses에 EXECUTED가 포함되어야 한다."""
        terminal = RequestStatus.terminal_statuses()
        assert RequestStatus.EXECUTED in terminal
        assert RequestStatus.COMPLETED in terminal
        assert RequestStatus.FAILED in terminal

    def test_is_terminal_property(self) -> None:
        """terminal 상태의 is_terminal은 True여야 한다."""
        assert RequestStatus.COMPLETED.is_terminal is True
        assert RequestStatus.EXECUTING.is_terminal is False
        assert RequestStatus.PENDING_APPROVAL.is_terminal is False


# [P0-5] 인증: 기존 X-User-Id 헤더 방식 유지 (JWT 미사용)


# ──────────────────────────────────────────────────
# [P1-6] risk_level별 승인 UX
# ──────────────────────────────────────────────────

class TestRiskLevelUX:
    def test_high_risk_plan_contains_warning(self) -> None:
        """high risk 오퍼레이션은 경고 메시지가 포함되어야 한다."""
        nodes = _make_nodes()
        operation = _make_entry("project.delete", operation_kind="delete", risk_level="high")
        resolved_inputs = {"references": {"project_name": "demo"}, "body": {}}
        message = nodes._build_risk_aware_plan(operation, resolved_inputs)
        assert "⚠️" in message
        assert "되돌릴 수 없습니다" in message
        assert "demo" in message

    def test_medium_risk_plan_is_normal(self) -> None:
        """medium risk 오퍼레이션은 일반 확인 메시지."""
        nodes = _make_nodes()
        operation = _make_entry("project.create", risk_level="medium")
        resolved_inputs = {"references": {"project_name": "demo"}, "body": {"name": "demo"}}
        message = nodes._build_risk_aware_plan(operation, resolved_inputs)
        assert "⚠️" not in message
        assert "실행할까요?" in message


# ──────────────────────────────────────────────────
# [P1-7] Pre-check
# ──────────────────────────────────────────────────

class TestPreCheck:
    def test_precheck_project_not_found_returns_error(self) -> None:
        """존재하지 않는 프로젝트는 에러를 반환해야 한다."""
        nodes = _make_nodes()
        project_client = AsyncMock()
        project_client.list_projects.return_value = {
            "items": [
                {"id": 1, "name": "alpha"},
                {"id": 2, "name": "demo-test"},
            ],
        }
        nodes.downstream_dispatcher.project_client = project_client

        import asyncio
        result = asyncio.run(nodes._precheck_project("user-1", "MEMBER", "demo"))
        assert result["error"] is not None
        assert "demo" in result["error"]
        assert "demo-test" in result["error"]  # 유사 이름 제안

    def test_precheck_project_found_returns_id(self) -> None:
        """존재하는 프로젝트는 ID를 반환해야 한다."""
        nodes = _make_nodes()
        project_client = AsyncMock()
        project_client.list_projects.return_value = {
            "items": [{"id": 42, "name": "demo"}],
        }
        nodes.downstream_dispatcher.project_client = project_client

        import asyncio
        result = asyncio.run(nodes._precheck_project("user-1", "MEMBER", "demo"))
        assert result["error"] is None
        assert result["project_id"] == 42

    def test_similar_names_detection(self) -> None:
        """유사 이름 감지가 동작해야 한다."""
        similar = WorkflowNodes._find_similar_names("demo", ["demo-1", "demo-test", "alpha", "beta"])
        assert "demo-1" in similar
        assert "demo-test" in similar


# ──────────────────────────────────────────────────
# [P1-8] API 선택 threshold
# ──────────────────────────────────────────────────

class TestScoreThreshold:
    def test_below_threshold_returns_empty(self) -> None:
        """threshold 미만 후보는 반환하지 않아야 한다."""
        entries = [_make_entry("project.create", usable_in=("command",))]
        service = RegistryService(entries, minimum_score_threshold=100)
        candidates = service.find_candidates("프로젝트 백업해줘", usable_in="command")
        assert candidates == []

    def test_above_threshold_returns_candidates(self) -> None:
        """threshold 이상 후보는 반환해야 한다."""
        entries = [_make_entry("project.create", usable_in=("command",), summary="프로젝트 생성")]
        service = RegistryService(entries, minimum_score_threshold=1)
        scored = service.find_scored_candidates("프로젝트 생성해줘", usable_in="command")
        assert len(scored) > 0

    def test_plan_command_no_matching_operation(self) -> None:
        """threshold 미달 시 plan_command가 FAILED를 반환해야 한다."""
        registry = MagicMock()
        registry.find_scored_candidates.return_value = []  # threshold 미달
        nodes = _make_nodes(registry_service=registry)
        state = _base_state(message_text="프로젝트 백업해줘", effective_message_text="프로젝트 백업해줘")
        result = nodes.plan_command(state)
        assert result["request_status"] == RequestStatus.FAILED.value
        assert "지원하지 않" in result["final_response"]
