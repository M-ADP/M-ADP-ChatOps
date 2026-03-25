from __future__ import annotations

from chatops.services.registry import RegistryEntry
from chatops.services.resolver import ParameterResolverService


def test_resolve_application_create_body_from_key_value_message() -> None:
    entry = RegistryEntry(
        id="application.create_apps",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps",
        method="POST",
        summary="애플리케이션 생성하기",
        capability="애플리케이션 생성하기",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("애플리케이션 생성",),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {
                "required": True,
                "required_fields": ["name", "cpu", "memory", "disk", "project_id", "port"],
            },
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="생성 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트에 앱 생성 name=demo cpu=1 memory=512 disk=10 port=8080",
    )

    assert resolved == {
        "body": {
            "name": "demo",
            "cpu": 1,
            "memory": 512,
            "disk": 10,
            "port": 8080,
        },
        "references": {"project_name": "demo"},
    }


def test_resolve_monitoring_path_from_message() -> None:
    entry = RegistryEntry(
        id="monitoring.get_app_deployment_traffic",
        source_file="apis/monitoring.yaml",
        operation_id="get_app_deployment_traffic",
        path="/monitoring/app-deployment/{project_id}/{app_deployment_name}",
        method="GET",
        summary="트래픽 조회",
        capability="트래픽 조회",
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=("X-User-Id",),
        required_inputs={
            "headers": [],
            "path": [
                {"name": "project_id", "required": True},
                {"name": "app_deployment_name", "required": True},
            ],
            "query": [],
            "body": None,
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="트래픽 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 api-server 앱 트래픽 조회",
    )

    assert resolved == {
        "path": {
            "app_deployment_name": "api-server",
        },
        "references": {
            "project_name": "demo",
            "application_name": "api-server",
        },
    }


def test_resolve_project_name_from_natural_language_message() -> None:
    entry = RegistryEntry(
        id="project.create",
        source_file="apis/project.yaml",
        operation_id="create_project",
        path="/projects",
        method="POST",
        summary="프로젝트 생성",
        capability="프로젝트 생성",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("프로젝트 생성",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {
                "required": True,
                "required_fields": ["name"],
            },
        },
        important_inputs={
            "path": [],
            "query": [],
            "body": ["name", "max_cpu", "max_memory", "max_disk"],
        },
        preconditions=(),
        missing_info_questions=("요청 본문의 name 값을 확인해야 합니다.",),
        response_interpretation="생성 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "프로젝트 하나 만들어줘. 이름은 chatops-human-demo야.",
    )

    assert resolved == {"body": {"name": "chatops-human-demo"}}


def test_resolve_project_create_important_resource_fields_from_natural_language() -> None:
    entry = RegistryEntry(
        id="project.create",
        source_file="apis/project.yaml",
        operation_id="create_project",
        path="/projects",
        method="POST",
        summary="프로젝트 생성",
        capability="프로젝트 생성",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("프로젝트 생성",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {
                "required": True,
                "required_fields": ["name"],
            },
        },
        important_inputs={
            "path": [],
            "query": [],
            "body": ["name", "max_cpu", "max_memory", "max_disk"],
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="생성 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "프로젝트 하나 만들어줘. 이름은 demo야. cpu는 1이야. 메모리는 0.5야. 디스크는 10이야.",
    )

    assert resolved == {
        "body": {
            "name": "demo",
            "max_cpu": 1,
            "max_memory": 0.5,
            "max_disk": 10,
        }
    }


def test_resolve_project_update_from_natural_language_message() -> None:
    entry = RegistryEntry(
        id="project.update_name",
        source_file="apis/project.yaml",
        operation_id="update_project_name",
        path="/projects/{project_id}/name",
        method="PATCH",
        summary="프로젝트 이름 수정",
        capability="프로젝트 이름 수정",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("프로젝트 이름 수정",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {
                "required": True,
                "required_fields": ["name"],
            },
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="수정 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 이름은 chatops-renamed로 바꿔줘",
    )

    assert resolved == {
        "body": {"name": "chatops-renamed"},
        "references": {"project_name": "demo"},
    }


def test_resolve_project_delete_from_short_natural_language_message() -> None:
    entry = RegistryEntry(
        id="project.delete",
        source_file="apis/project.yaml",
        operation_id="delete_project",
        path="/projects/{project_id}",
        method="DELETE",
        summary="프로젝트 삭제",
        capability="프로젝트 삭제",
        usable_in=("command",),
        operation_kind="delete",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="high",
        side_effects=("프로젝트 삭제",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": None,
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="삭제 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 지워줘",
    )

    assert resolved == {"references": {"project_name": "demo"}}


def test_resolve_project_update_uses_previous_message_context_for_pronoun_reference() -> None:
    entry = RegistryEntry(
        id="project.update_name",
        source_file="apis/project.yaml",
        operation_id="update_project_name",
        path="/projects/{project_id}/name",
        method="PATCH",
        summary="프로젝트 이름 수정",
        capability="프로젝트 이름 수정",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("프로젝트 이름 수정",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {"required": True, "required_fields": ["name"]},
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="수정 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "그거 이름은 chatops-renamed로 바꿔줘",
        session_context={"last_message_text": "demo 프로젝트 만들어줘"},
    )

    assert resolved == {
        "body": {"name": "chatops-renamed"},
        "references": {"project_name": "demo"},
    }


def test_resolve_project_add_member_from_natural_language_message() -> None:
    entry = RegistryEntry(
        id="project.add_member",
        source_file="apis/project.yaml",
        operation_id="add_project_member",
        path="/projects/{project_id}/members",
        method="POST",
        summary="프로젝트 멤버 추가",
        capability="프로젝트 멤버 추가",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=("프로젝트 멤버 추가",),
        required_headers=("X-User-Id", "X-User-Role"),
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {"required": True, "required_fields": ["user_id"]},
        },
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="추가 결과",
        plan_template=(),
        examples=(),
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트에 alice 멤버 추가해줘",
    )

    assert resolved == {
        "references": {"project_name": "demo", "target_nickname": "alice"},
    }


def test_korean_unit_giga_in_memory_field() -> None:
    """'메모리는 1기가' 표현을 처리한다."""
    entry = RegistryEntry(
        id="project.create",
        source_file="apis/project.yaml",
        operation_id=None,
        path="/projects",
        method="POST",
        summary="프로젝트 생성",
        capability="프로젝트 생성",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=(),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["name"]},
        },
        important_inputs={
            "path": [],
            "query": [],
            "body": ["name", "max_cpu", "max_memory", "max_disk"],
        },
    )
    resolver = ParameterResolverService()
    resolved = resolver.resolve(entry, "이름은 demo야 cpu는 1이야 메모리는 2기가 디스크는 10gb")
    body = resolved.get("body", {})
    assert body.get("max_memory") == 2
    assert body.get("max_disk") == 10


def test_korean_number_cpu_hana() -> None:
    """'cpu는 하나' 표현을 처리한다."""
    entry = RegistryEntry(
        id="project.create",
        source_file="apis/project.yaml",
        operation_id=None,
        path="/projects",
        method="POST",
        summary="프로젝트 생성",
        capability="프로젝트 생성",
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=(),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": {"required": True, "required_fields": ["name"]},
        },
        important_inputs={
            "path": [],
            "query": [],
            "body": ["name", "max_cpu", "max_memory", "max_disk"],
        },
    )
    resolver = ParameterResolverService()
    resolved = resolver.resolve(entry, "이름은 demo야 cpu는 하나 메모리는 1이야 디스크는 10이야")
    body = resolved.get("body", {})
    assert body.get("max_cpu") == 1


def test_entity_memory_resolves_project_from_previous_request() -> None:
    """'그 프로젝트' 표현이 이전 요청의 entity memory에서 프로젝트명을 가져온다."""
    entry = RegistryEntry(
        id="project.delete",
        source_file="apis/project.yaml",
        operation_id=None,
        path="/projects/{project_id}",
        method="DELETE",
        summary="프로젝트 삭제",
        capability="프로젝트 삭제",
        usable_in=("command",),
        operation_kind="delete",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="high",
        side_effects=(),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": None,
        },
    )
    resolver = ParameterResolverService()
    resolved = resolver.resolve(
        entry,
        "그 프로젝트 삭제해줘",
        session_context={
            "last_resolved_references": {"project_name": "demo", "application_name": "api-demo"},
        },
    )
    assert resolved.get("references", {}).get("project_name") == "demo"


def test_entity_memory_resolves_app_from_previous_request() -> None:
    """'방금 만든 앱' 표현이 이전 entity memory에서 앱명을 가져온다."""
    entry = RegistryEntry(
        id="application.delete_apps",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps",
        method="DELETE",
        summary="애플리케이션 삭제",
        capability="애플리케이션 삭제",
        usable_in=("command",),
        operation_kind="delete",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="high",
        side_effects=(),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [],
            "body": None,
        },
        important_inputs={"path": [], "query": [], "body": ["project_id", "application_id"]},
    )
    resolver = ParameterResolverService()
    resolved = resolver.resolve(
        entry,
        "방금 만든 앱 삭제해줘",
        session_context={
            "last_resolved_references": {"project_name": "demo", "application_name": "api-demo"},
        },
    )
    refs = resolved.get("references", {})
    assert refs.get("project_name") == "demo"
    assert refs.get("application_name") == "api-demo"
