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
                "required_fields": ["name", "cpu", "memory", "disk", "project_id"],
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
        },
        "references": {"project_name": "demo"},
    }


def test_resolve_application_create_project_name_from_target_project_label() -> None:
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
                "required_fields": ["name", "cpu", "memory", "disk", "project_id"],
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
        "어플리케이션 생성해, 앱 이름 : heyblackk, CPU 1, 메모리 1.2, 디스크 1, 대상 프로젝트 : killblack",
    )

    assert resolved == {
        "body": {
            "name": "heyblackk",
            "cpu": 1,
            "memory": 1.2,
            "disk": 1,
        },
        "references": {"project_name": "killblack"},
    }


def test_resolve_application_create_ignores_invalid_key_value_port_token() -> None:
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
                "required_fields": ["name", "cpu", "memory", "disk", "project_id"],
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
        "demo 프로젝트에 앱 생성 name=demo cpu=1 memory=512 disk=10 port: 포트: 8080",
    )

    assert resolved == {
        "body": {
            "name": "demo",
            "cpu": 1,
            "memory": 512,
            "disk": 10,
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


def test_resolve_monitoring_time_range_from_natural_language() -> None:
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
            "query": [
                {"name": "start", "required": False},
                {"name": "end", "required": False},
            ],
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
        "demo 프로젝트 api-server 앱 최근 1시간 트래픽 보여줘",
    )

    assert resolved["path"]["app_deployment_name"] == "api-server"
    assert resolved["references"] == {
        "project_name": "demo",
        "application_name": "api-server",
    }
    assert "start" in resolved["query"]
    assert "end" in resolved["query"]
    assert resolved["query"]["start"] < resolved["query"]["end"]


def test_resolve_monitoring_time_range_from_explicit_dates() -> None:
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
            "query": [
                {"name": "start", "required": False},
                {"name": "end", "required": False},
            ],
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
        "demo 프로젝트 api-server 앱 2026-03-28부터 2026-03-29까지 트래픽 보여줘",
    )

    assert resolved["references"] == {
        "project_name": "demo",
        "application_name": "api-server",
    }
    assert resolved["query"]["start"].startswith("2026-03-28T00:00:00")
    assert resolved["query"]["end"].startswith("2026-03-29T23:59:59")


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


def test_resolve_application_resource_update_from_colloquial_message() -> None:
    entry = RegistryEntry(
        id="application.patch_apps_resources",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps/resources",
        method="PATCH",
        summary="애플리케이션 리소스 변경",
        capability="애플리케이션 리소스 변경",
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
            "body": {"required": True, "required_fields": ["application_id"]},
        },
        important_inputs={
            "path": [],
            "query": [],
            "body": ["project_id", "application_id", "max_cpu", "max_memory", "max_disk"],
        },
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 api 앱 cpu는 한 개반으로, 메모리는 1024메가로, 디스크는 20기가로 늘려줘",
    )

    assert resolved == {
        "body": {
            "max_cpu": 1.5,
            "max_memory": 1024,
            "max_disk": 20,
        },
        "references": {
            "project_name": "demo",
            "application_name": "api",
        },
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


def test_resolve_project_update_resource_from_natural_language_message() -> None:
    entry = RegistryEntry(
        id="project.update_resource",
        source_file="apis/project.yaml",
        operation_id="update_project_resource",
        path="/projects/{project_id}/resource",
        method="PATCH",
        summary="프로젝트 리소스 수정",
        capability="프로젝트 리소스 수정",
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
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {"required": True, "required_fields": ["max_cpu", "max_memory", "max_disk"]},
        },
        important_inputs={"path": [], "query": [], "body": ["max_cpu", "max_memory", "max_disk"]},
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 리소스 변경해줘 cpu는 2 메모리는 4 디스크는 20이야",
    )

    assert resolved == {
        "body": {"max_cpu": 2, "max_memory": 4, "max_disk": 20},
        "references": {"project_name": "demo"},
    }


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


def test_resolve_application_logs_query_from_natural_language_message() -> None:
    entry = RegistryEntry(
        id="application.get_apps_logs",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps/logs",
        method="GET",
        summary="앱 로그 조회",
        capability="앱 로그 조회",
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [
                {"name": "project_id", "required": True},
                {"name": "app_name", "required": True},
            ],
            "body": None,
        },
        important_inputs={"path": [], "query": ["project_id", "app_name"], "body": []},
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 api-demo 앱 로그 보여줘",
    )

    assert resolved == {
        "query": {"app_name": "api-demo"},
        "references": {"project_name": "demo", "application_name": "api-demo"},
    }


def test_resolve_application_list_query_from_natural_language_message() -> None:
    entry = RegistryEntry(
        id="application.get_apps",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps",
        method="GET",
        summary="앱 목록 조회",
        capability="앱 목록 조회",
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=(),
        required_inputs={
            "headers": [],
            "path": [],
            "query": [{"name": "project_id", "required": True}],
            "body": None,
        },
        important_inputs={"path": [], "query": ["project_id"], "body": []},
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 앱 목록 보여줘",
    )

    assert resolved == {"references": {"project_name": "demo"}}


def test_resolve_project_resource_correction_prefers_last_value() -> None:
    entry = RegistryEntry(
        id="project.update_resource",
        source_file="apis/project.yaml",
        operation_id="update_project_resource",
        path="/projects/{project_id}/resource",
        method="PATCH",
        summary="프로젝트 리소스 수정",
        capability="프로젝트 리소스 수정",
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
            "path": [{"name": "project_id", "required": True}],
            "query": [],
            "body": {"required": True, "required_fields": ["max_cpu", "max_memory", "max_disk"]},
        },
        important_inputs={"path": [], "query": [], "body": ["max_cpu", "max_memory", "max_disk"]},
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 리소스 변경해줘 cpu는 1 아니고 2 메모리는 2 디스크는 20이야",
    )

    assert resolved["body"]["max_cpu"] == 2


def test_resolve_github_branch_correction_prefers_replacement_value() -> None:
    entry = RegistryEntry(
        id="application.patch_apps_github",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps/github",
        method="PATCH",
        summary="앱 깃허브 연결",
        capability="앱 깃허브 연결",
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
            "body": {"required": True, "required_fields": ["owner", "repository", "branch"]},
        },
        important_inputs={"path": [], "query": [], "body": ["owner", "repository", "branch"]},
    )

    resolved = ParameterResolverService().resolve(
        entry,
        "demo 프로젝트 api-demo 앱 깃허브 연결해줘 owner는 acme repository는 portal branch는 main 말고 develop이야",
    )

    assert resolved["references"] == {"project_name": "demo", "application_name": "api-demo"}
    assert resolved["body"]["owner"] == "acme"
    assert resolved["body"]["repository"] == "portal"
    assert resolved["body"]["branch"] == "develop"


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


def test_entity_memory_reuses_resolved_ids_from_persistent_state() -> None:
    entry = RegistryEntry(
        id="application.patch_apps_resources",
        source_file="apis/application.yaml",
        operation_id=None,
        path="/apps/resources",
        method="PATCH",
        summary="애플리케이션 리소스 변경",
        capability="애플리케이션 리소스 변경",
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
            "body": {"required": True, "required_fields": ["application_id"]},
        },
        important_inputs={"path": [], "query": [], "body": ["application_id", "max_cpu"]},
    )

    resolver = ParameterResolverService()
    resolved = resolver.resolve(
        entry,
        "그 앱 cpu는 2로 바꿔줘",
        session_context={
            "entity_memory": {
                "projects": [
                    {"canonical_name": "demo", "aliases": ["demo"], "resolved_id": 98},
                ],
                "applications": [
                    {
                        "canonical_name": "api-demo",
                        "aliases": ["api-demo", "api"],
                        "project_name": "demo",
                        "project_id": 98,
                        "resolved_id": 777,
                    }
                ],
            }
        },
    )

    assert resolved["references"] == {"project_name": "demo", "application_name": "api-demo"}
    assert resolved["resolved_ids"] == {"project_id": 98, "application_id": 777}


def test_entity_memory_reuses_target_user_id_from_user_aliases() -> None:
    entry = RegistryEntry(
        id="project.remove_member",
        source_file="apis/project.yaml",
        operation_id=None,
        path="/projects/{project_id}/members/{target_user_id}",
        method="DELETE",
        summary="프로젝트 멤버 제거",
        capability="프로젝트 멤버 제거",
        usable_in=("command",),
        operation_kind="delete",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
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
        "그 멤버 제거해줘",
        session_context={
            "entity_memory": {
                "projects": [
                    {"canonical_name": "demo", "aliases": ["demo"], "resolved_id": 98},
                ],
                "users": [
                    {
                        "canonical_name": "alice",
                        "nickname": "alice",
                        "aliases": ["alice", "alice.sre"],
                        "project_name": "demo",
                        "project_id": 98,
                        "resolved_id": 321,
                    }
                ],
            }
        },
    )

    assert resolved["references"] == {"project_name": "demo", "target_nickname": "alice"}
    assert resolved["resolved_ids"] == {"project_id": 98, "target_user_id": 321}
