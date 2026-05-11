from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chatops.graph.agent_loop import AgentStepContext
from chatops.services.registry import RegistryEntry, RegistryService


def test_query_mode_returns_only_read_operations() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("프로젝트 목록 보여줘", usable_in="query")

    assert candidates
    assert all(candidate.operation_kind == "read" for candidate in candidates)
    assert all(candidate.requires_confirmation is False for candidate in candidates)


def test_query_mode_prefers_project_list_for_natural_language_queries() -> None:
    service = RegistryService.from_directory("ai_registry")

    for user_text in ("프로젝트 목록 보여줘", "프로젝트 리스트 알려줘"):
        candidates = service.find_candidates(user_text, usable_in="query")

        assert candidates
        assert candidates[0].id == "project.list_projects"


def test_query_mode_returns_member_list_when_member_context_is_present() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트 멤버 목록 보여줘", usable_in="query")

    assert candidates
    assert candidates[0].id == "project.list_members"


def test_query_mode_prefers_project_member_list_for_member_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트 멤버 목록 보여줘", usable_in="query")

    assert candidates
    assert candidates[0].id == "project.list_members"


def test_query_mode_prefers_project_resource_limit_for_limit_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트 리소스 한도 보여줘", usable_in="query")

    assert candidates
    assert candidates[0].id == "project.get_resource_limit"


def test_query_mode_prefers_application_logs_for_log_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트 api-demo 앱 로그 보여줘", usable_in="query")

    assert candidates
    assert candidates[0].id == "application.get_apps_logs"


def test_query_mode_prefers_application_details_for_detail_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트 api-demo 앱 상세 보여줘", usable_in="query")

    assert candidates
    assert candidates[0].id == "application.get_apps_details"


def test_query_mode_prefers_application_status_for_status_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트 api-demo 앱 상태 보여줘", usable_in="query")

    assert candidates
    assert candidates[0].id == "application.get_apps_status"


def test_command_mode_returns_only_mutating_operations() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("프로젝트 생성해줘", usable_in="command")

    assert candidates
    assert candidates[0].id == "project.create"
    assert all(candidate.operation_kind in {"write", "delete", "action"} for candidate in candidates)


def test_command_mode_prefers_operation_matching_required_inputs() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "앱 생성 name=demo cpu=1 memory=512 disk=10 project_id=98 port=8080",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "application.create_apps"


def test_command_mode_prefers_project_update_for_rename_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "프로젝트 id는 98이고 이름은 chatops-renamed로 바꿔줘",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "project.update_name"


def test_command_mode_prefers_project_delete_for_short_delete_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "프로젝트 98 지워줘",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "project.delete"


def test_command_mode_prefers_project_update_resource_for_resource_update_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "demo 프로젝트 리소스 늘려줘",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "project.update_resource"


def test_command_mode_prefers_application_create_for_natural_language_create_requests() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "demo 프로젝트에 앱 만들어줘",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "application.create_apps"


def test_command_mode_prefers_application_create_for_incomplete_application_requests() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "애플리케이션 생성해",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "application.create_apps"


def test_command_mode_prefers_application_create_for_eopeulrikeshyeon_synonym() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "어플리케이션 생성해, 앱 이름 : heyblackk, CPU 1, 메모리 1.2, 디스크 1, 대상 프로젝트 : killblack",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "application.create_apps"


def test_command_mode_prefers_application_delete_for_delete_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "demo 프로젝트 api-demo 앱 삭제해줘",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "application.delete_apps"


def test_command_mode_prefers_application_resource_update_for_resource_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "demo 프로젝트 api-demo 앱 리소스 늘려줘",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "application.patch_apps_resources"


def test_command_mode_prefers_application_github_update_for_github_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates(
        "demo 프로젝트 api-demo 앱 깃허브 연결해줘",
        usable_in="command",
    )

    assert candidates
    assert candidates[0].id == "application.patch_apps_github"


def test_command_mode_prefers_project_add_member_for_member_add_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트에 alice 멤버 추가해줘", usable_in="command")

    assert candidates
    assert candidates[0].id == "project.invite_member"


def test_command_mode_prefers_project_remove_member_for_member_remove_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트에서 alice 멤버 제거해줘", usable_in="command")

    assert candidates
    assert candidates[0].id == "project.remove_member"


def test_command_mode_prefers_project_transfer_ownership_for_owner_transfer_language() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("demo 프로젝트 소유권을 alice에게 넘겨줘", usable_in="command")

    assert candidates
    assert candidates[0].id == "project.transfer_ownership"


def test_supported_command_entries_define_important_inputs() -> None:
    service = RegistryService.from_directory("ai_registry")

    project_create = service.get_entry("project.create")
    application_create = service.get_entry("application.create_apps")
    project_update_resource = service.get_entry("project.update_resource")
    application_delete = service.get_entry("application.delete_apps")
    application_resource = service.get_entry("application.patch_apps_resources")
    application_github = service.get_entry("application.patch_apps_github")

    assert project_create is not None
    assert project_create.important_inputs["body"] == ["name", "max_cpu", "max_memory", "max_disk"]

    assert application_create is not None
    assert application_create.important_inputs["body"] == ["project_id", "name", "cpu", "memory", "disk"]

    assert project_update_resource is not None
    assert project_update_resource.important_inputs["body"] == ["max_cpu", "max_memory", "max_disk"]
    assert application_delete is not None
    assert application_delete.important_inputs["body"] == ["project_id", "application_id"]
    assert application_resource is not None
    assert application_resource.important_inputs["body"] == ["project_id", "application_id", "max_cpu", "max_memory", "max_disk"]
    assert application_github is not None
    assert application_github.important_inputs["body"] == ["project_id", "appDeploymentId", "owner", "repository", "branch"]


def test_command_mode_excludes_unsupported_operations_from_candidates() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("프로젝트 멤버 추가해줘", usable_in="command", limit=20)

    candidate_ids = {candidate.id for candidate in candidates}
    assert "project.invite_member" in candidate_ids
    assert "project.remove_member" in candidate_ids
    assert candidates[0].id == "project.invite_member"


# ──────────────────────────────────────────────────
# Follow-up Router 테스트
# ──────────────────────────────────────────────────


def _make_entry(
    entry_id: str,
    *,
    operation_kind: str = "read",
    capability: str = "",
    summary: str = "",
    usable_in: tuple[str, ...] = ("query",),
) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file=f"{entry_id}.ai.yaml",
        operation_id=entry_id.split(".", 1)[1],
        path=f"/{entry_id.replace('.', '/')}",
        method="GET" if operation_kind == "read" else "POST",
        summary=summary or entry_id,
        capability=capability or entry_id,
        usable_in=usable_in,
        operation_kind=operation_kind,
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=(),
    )


@dataclass
class StubSemanticRouter:
    """find_agent_candidates 테스트용 결정론적 임베딩 stub.

    embed_text가 받은 텍스트를 그대로 anchor로 매칭한다.
    score_bonus는 keyword-based로 동작 — operation_id별 keyword 매칭이 있으면 보너스.
    """

    keyword_bonus: dict[str, dict[str, int]] = field(default_factory=dict)
    last_embed_text: str | None = None

    def embed_text(self, text: str) -> list[float] | None:
        self.last_embed_text = text
        # non-None 벡터를 반환해야 fallback 분기 회피
        return [1.0]

    def score_bonus(self, user_vec: list[float], operation_id: str) -> int:
        text = self.last_embed_text or ""
        bonus = 0
        for keyword, score in self.keyword_bonus.get(operation_id, {}).items():
            if keyword in text:
                bonus = max(bonus, score)
        return bonus


def test_find_agent_candidates_step_context_none_keeps_legacy_behavior() -> None:
    """step_context 미지정 시 기존 동작과 동일해야 한다 — 회귀 방지."""
    entries = [
        _make_entry("project.list_projects", capability="project list 목록"),
        _make_entry("application.list_apps", capability="application list 목록"),
        _make_entry("project.check_available", capability="precheck"),
    ]
    router = StubSemanticRouter(
        keyword_bonus={
            "project.list_projects": {"project": 20},
            "application.list_apps": {"application": 20},
        }
    )
    service = RegistryService(
        entries=entries,
        minimum_score_threshold=1,
        semantic_router=router,
    )

    candidates = service.find_agent_candidates("project list 보여줘")
    ids = [c.id for c in candidates]

    assert "project.list_projects" in ids
    # 항상 포함 도구
    assert "project.check_available" in ids


def test_find_agent_candidates_followup_composes_tool_result_into_embed_query() -> None:
    """followup 모드에서 latest_tool_result_summary가 임베딩 쿼리에 합성되어야 한다."""
    entries = [
        _make_entry("project.list_projects", capability="project list"),
        _make_entry("application.create_apps", operation_kind="write", capability="application create"),
        _make_entry("project.check_available", capability="precheck"),
    ]
    router = StubSemanticRouter()
    service = RegistryService(
        entries=entries,
        minimum_score_threshold=1,
        semantic_router=router,
    )

    ctx = AgentStepContext(
        original_user_text="프로젝트 X 만들고 그 안에 앱 만들어줘",
        executed_operation_ids=("project.list_projects",),
        latest_tool_result_summary="[ok] project.list_projects → Found project 'X' id=42",
        last_result_success=True,
        candidate_mode="followup",
    )

    service.find_agent_candidates(ctx.original_user_text, step_context=ctx)

    # 임베딩 호출이 합성 텍스트로 이루어졌는지 검증
    assert router.last_embed_text is not None
    assert "프로젝트 X" in router.last_embed_text
    assert "[ok] project.list_projects" in router.last_embed_text


def test_find_agent_candidates_followup_penalizes_already_executed() -> None:
    """이미 실행한 operation은 score 감점되어 threshold 미달 시 후보에서 빠진다."""
    # 두 entry는 동일하게 의미 보너스 6점을 받아 동률 — penalty -5가 결정적으로 작용
    entries = [
        _make_entry("foo.executed_op", capability="중립캡"),
        _make_entry("foo.other_op", capability="중립캡"),
        _make_entry("project.check_available", capability="precheck"),
    ]
    router = StubSemanticRouter(
        keyword_bonus={
            "foo.executed_op": {"중립쿼리": 6},
            "foo.other_op": {"중립쿼리": 6},
        }
    )
    service = RegistryService(
        entries=entries,
        minimum_score_threshold=5,
        semantic_router=router,
    )

    # latest_tool_result_summary는 비워서 합성 텍스트 오염을 막는다
    ctx = AgentStepContext(
        original_user_text="중립쿼리",
        executed_operation_ids=("foo.executed_op",),
        latest_tool_result_summary="",
        last_result_success=True,
        candidate_mode="followup",
    )

    candidates = service.find_agent_candidates(ctx.original_user_text, step_context=ctx)
    ids = [c.id for c in candidates]

    # executed_op는 6 - 5(penalty) = 1점 → threshold(5) 미달로 후보에서 빠진다.
    # other_op는 6점 그대로 유지되어 후보에 남는다.
    assert "foo.other_op" in ids
    assert "foo.executed_op" not in ids


def test_find_agent_candidates_recovery_boosts_failed_domain_read_tools() -> None:
    """recovery 모드에서 실패 도메인의 read 도구가 부스트되어 후보에 들어온다."""
    entries = [
        _make_entry("project.list_projects", capability="조회"),  # 같은 도메인 read
        _make_entry("project.get_resource_limit", capability="조회"),  # 같은 도메인 read
        _make_entry("application.create_apps", operation_kind="write", capability="조회"),
    ]
    # 스코어가 0이라도 recovery 보너스로 통과해야 한다
    router = StubSemanticRouter(keyword_bonus={})
    service = RegistryService(
        entries=entries,
        minimum_score_threshold=10,  # 보너스 없이는 통과 불가능한 threshold
        semantic_router=router,
    )

    ctx = AgentStepContext(
        original_user_text="아무 텍스트",
        executed_operation_ids=("project.create",),
        latest_tool_result_summary="[failed] project.create → 422 missing name",
        last_result_success=False,
        candidate_mode="recovery",
    )

    candidates = service.find_agent_candidates(ctx.original_user_text, step_context=ctx)
    ids = {c.id for c in candidates}

    # 같은 도메인 read 도구가 보너스 + 완화된 threshold(=5)로 후보에 들어온다
    assert "project.list_projects" in ids
    assert "project.get_resource_limit" in ids


def test_find_agent_candidates_empty_uses_safe_fallback_not_all_enabled() -> None:
    """후보가 비면 all_enabled 전체가 아닌 score 상위 N으로 제한된 fallback을 쓴다."""
    # 모든 entry가 threshold 미달이 되도록 구성
    entries = [_make_entry(f"domain.op{i}") for i in range(12)]
    entries.append(_make_entry("project.check_available", capability="precheck"))
    router = StubSemanticRouter(keyword_bonus={})  # 모든 보너스 0
    service = RegistryService(
        entries=entries,
        minimum_score_threshold=100,  # 절대 통과 불가
        semantic_router=router,
    )

    ctx = AgentStepContext(
        original_user_text="아무 텍스트",
        executed_operation_ids=("foo.bar",),
        latest_tool_result_summary="",
        last_result_success=True,
        candidate_mode="followup",
    )

    candidates = service.find_agent_candidates(ctx.original_user_text, step_context=ctx)

    # all_enabled (13개) 전체가 아니라 top-N(5) + always-included 정도로 제한된다
    assert 0 < len(candidates) < len(entries)

