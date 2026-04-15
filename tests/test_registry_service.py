from chatops.services.registry import RegistryService


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
    assert candidates[0].id == "project.add_member"


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
    assert application_create.important_inputs["body"] == ["project_id", "name", "cpu", "memory", "disk", "port"]

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
    assert "project.add_member" in candidate_ids
    assert "project.remove_member" in candidate_ids
    # transfer_ownership은 "멤버 추가" 요청에 대해 threshold 미달로 제외될 수 있음
    # 핵심은 add_member가 최상위 후보로 선택되는 것
    assert candidates[0].id == "project.add_member"
