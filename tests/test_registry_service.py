from chatops.services.registry import RegistryService


def test_query_mode_returns_only_read_operations() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("프로젝트 목록 보여줘", usable_in="query")

    assert candidates
    assert all(candidate.operation_kind == "read" for candidate in candidates)
    assert all(candidate.requires_confirmation is False for candidate in candidates)


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
