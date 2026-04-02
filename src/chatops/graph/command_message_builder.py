from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommandMessageBuilder:
    def format_missing_input_response(self, operation, missing_inputs: list[str]) -> str:
        labels = [self.format_missing_input_prompt_label(operation.id, field_name) for field_name in missing_inputs]
        joined_labels = ", ".join(labels)
        return f"{self._missing_input_intro(operation.id)} 아래 정보가 더 필요합니다. {joined_labels}를 알려주세요."

    def format_missing_input_prompt_label(self, operation_id: str, field_name: str) -> str:
        if operation_id.startswith("application.") and field_name == "name":
            return "앱 이름"
        labels = {
            "name": "프로젝트 이름",
            "project_name": "대상 프로젝트",
            "application_name": "앱 이름",
            "application_id": "앱 이름",
            "appDeploymentId": "앱 이름",
            "target_nickname": "대상 사용자 닉네임",
            "cpu": "CPU",
            "max_cpu": "최대 CPU",
            "memory": "메모리",
            "max_memory": "최대 메모리",
            "disk": "디스크",
            "max_disk": "최대 디스크",
            "port": "포트",
            "owner": "GitHub 소유자",
            "repository": "저장소 이름",
            "branch": "브랜치",
        }
        return labels.get(field_name, field_name)

    def format_query_missing_input_response(self, operation_id: str, missing_inputs: list[str]) -> str:
        normalized = list(dict.fromkeys(missing_inputs))
        if {"project_name", "application_name"}.issubset(set(normalized)):
            return "어느 프로젝트의 어떤 앱인지 알려주세요."
        labels = [self.format_missing_input_prompt_label(operation_id, field_name) for field_name in normalized]
        if len(labels) == 1:
            return f"{labels[0]}을(를) 알려주세요."
        return f"{', '.join(labels)} 정보를 알려주세요."

    def collect_inquiry_inputs(self, operation) -> list[str]:
        labels: list[str] = []
        for section_name in ("path", "query", "body"):
            for field_name in operation.important_inputs.get(section_name, []):
                normalized = self._normalize_input_name(field_name)
                if not normalized:
                    continue
                label_key = self._to_user_input_field(normalized)
                labels.append(self.format_missing_input_prompt_label(operation.id, label_key))
        if not labels and isinstance(operation.required_inputs.get("body"), dict):
            for field_name in operation.required_inputs["body"].get("required_fields", []):
                label_key = self._to_user_input_field(str(field_name))
                labels.append(self.format_missing_input_prompt_label(operation.id, label_key))
        return list(dict.fromkeys(labels))

    def build_command_plan(self, operation, resolved_inputs: dict[str, Any]) -> str:
        references = resolved_inputs.get("references", {})
        body_values = resolved_inputs.get("body", {})
        details: list[str] = []

        if operation.id == "project.create":
            name = body_values.get("name") or references.get("project_name")
            if name:
                details.append(f"프로젝트 이름 {name}")
            if body_values.get("max_cpu") is not None:
                details.append(f"최대 CPU {body_values['max_cpu']}")
            if body_values.get("max_memory") is not None:
                details.append(f"최대 메모리 {body_values['max_memory']}GB")
            if body_values.get("max_disk") is not None:
                details.append(f"최대 디스크 {body_values['max_disk']}GB")
            return self._compose_plan_message("프로젝트를 생성할게요.", details)

        if operation.id == "project.update_name":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if body_values.get("name"):
                details.append(f"새 이름 {body_values['name']}")
            return self._compose_plan_message("프로젝트 이름을 변경할게요.", details)

        if operation.id == "project.delete":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            return self._compose_plan_message("프로젝트를 삭제할게요.", details)

        if operation.id == "project.add_member":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if references.get("target_nickname"):
                details.append(f"추가할 사용자 {references['target_nickname']}")
            return self._compose_plan_message("프로젝트 멤버를 추가할게요.", details)

        if operation.id == "project.remove_member":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if references.get("target_nickname"):
                details.append(f"제거할 사용자 {references['target_nickname']}")
            return self._compose_plan_message("프로젝트 멤버를 제거할게요.", details)

        if operation.id == "project.transfer_ownership":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if references.get("target_nickname"):
                details.append(f"새 소유자 {references['target_nickname']}")
            return self._compose_plan_message("프로젝트 소유권을 이전할게요.", details)

        if operation.id == "project.update_resource":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if body_values.get("max_cpu") is not None:
                details.append(f"최대 CPU {body_values['max_cpu']}")
            if body_values.get("max_memory") is not None:
                details.append(f"최대 메모리 {body_values['max_memory']}GB")
            if body_values.get("max_disk") is not None:
                details.append(f"최대 디스크 {body_values['max_disk']}GB")
            return self._compose_plan_message("프로젝트 리소스를 변경할게요.", details)

        if operation.id == "application.create_apps":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            app_name = body_values.get("name") or references.get("application_name")
            if app_name:
                details.append(f"앱 이름 {app_name}")
            if body_values.get("cpu") is not None:
                details.append(f"CPU {body_values['cpu']}")
            if body_values.get("memory") is not None:
                details.append(f"메모리 {body_values['memory']}MB")
            if body_values.get("disk") is not None:
                details.append(f"디스크 {body_values['disk']}GB")
            if body_values.get("port") is not None:
                details.append(f"포트 {body_values['port']}")
            return self._compose_plan_message("애플리케이션을 생성할게요.", details)

        if operation.id == "application.delete_apps":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if references.get("application_name"):
                details.append(f"앱 이름 {references['application_name']}")
            return self._compose_plan_message("애플리케이션을 삭제할게요.", details)

        if operation.id == "application.patch_apps_resources":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if references.get("application_name"):
                details.append(f"앱 이름 {references['application_name']}")
            if body_values.get("max_cpu") is not None:
                details.append(f"최대 CPU {body_values['max_cpu']}")
            if body_values.get("max_memory") is not None:
                details.append(f"최대 메모리 {body_values['max_memory']}MB")
            if body_values.get("max_disk") is not None:
                details.append(f"최대 디스크 {body_values['max_disk']}GB")
            return self._compose_plan_message("애플리케이션 자원을 변경할게요.", details)

        if operation.id == "application.patch_apps_github":
            if references.get("project_name"):
                details.append(f"대상 프로젝트 {references['project_name']}")
            if references.get("application_name"):
                details.append(f"앱 이름 {references['application_name']}")
            if body_values.get("owner"):
                details.append(f"GitHub 소유자 {body_values['owner']}")
            if body_values.get("repository"):
                details.append(f"저장소 {body_values['repository']}")
            if body_values.get("branch"):
                details.append(f"브랜치 {body_values['branch']}")
            return self._compose_plan_message("애플리케이션 GitHub 연결 정보를 변경할게요.", details)

        capability = operation.capability or operation.summary or "작업"
        capability = capability.replace("Endpoint", "").strip()
        details.extend(f"{label} {value}" for label, value in self._user_visible_parameters(resolved_inputs))
        return self._compose_plan_message(f"{capability} 작업을 진행할게요.", details)

    def build_command_success_message(self, operation_id: str, summary: str) -> str:
        messages = {
            "project.create": "프로젝트를 생성했습니다. 프로젝트 설정을 변경하거나 앱을 추가할 수 있습니다.",
            "project.update_name": "프로젝트 이름을 변경했습니다.",
            "project.update_resource": "프로젝트 리소스를 변경했습니다.",
            "project.delete": "프로젝트를 삭제했습니다.",
            "project.add_member": "프로젝트 멤버를 추가했습니다.",
            "project.remove_member": "프로젝트 멤버를 제거했습니다.",
            "project.transfer_ownership": "프로젝트 소유권을 이전했습니다.",
            "application.create_apps": "애플리케이션을 생성했습니다. GitHub 연결이나 리소스 설정을 진행할 수 있습니다.",
            "application.delete_apps": "애플리케이션을 삭제했습니다.",
            "application.patch_apps_resources": "애플리케이션 자원을 변경했습니다.",
            "application.patch_apps_github": "애플리케이션 GitHub 연결 정보를 변경했습니다.",
        }
        return messages.get(operation_id, f"요청한 작업을 완료했습니다. {summary}")

    def build_command_failure_message(self, operation_id: str, summary: str) -> str:
        subjects = {
            "project.create": "프로젝트 생성",
            "project.update_name": "프로젝트 이름 변경",
            "project.update_resource": "프로젝트 리소스 변경",
            "project.delete": "프로젝트 삭제",
            "project.add_member": "프로젝트 멤버 추가",
            "project.remove_member": "프로젝트 멤버 제거",
            "project.transfer_ownership": "프로젝트 소유권 이전",
            "application.create_apps": "애플리케이션 생성",
            "application.delete_apps": "애플리케이션 삭제",
            "application.patch_apps_resources": "애플리케이션 자원 변경",
            "application.patch_apps_github": "애플리케이션 GitHub 연결 정보 변경",
        }
        subject = subjects.get(operation_id, "요청한 작업")
        if summary and summary.strip():
            return f"{subject}에 실패했습니다. {summary} 입력값을 확인하고 다시 시도해주세요."
        return f"{subject}에 실패했습니다. 입력값을 확인하고 다시 시도해주세요."

    def _user_visible_parameters(self, resolved_inputs: dict[str, Any]) -> list[tuple[str, Any]]:
        references = resolved_inputs.get("references", {})
        body_values = resolved_inputs.get("body", {})
        query_values = resolved_inputs.get("query", {})
        visible: list[tuple[str, Any]] = []

        for key, value in references.items():
            if key == "project_name":
                visible.append(("프로젝트", value))
            elif key == "application_name":
                visible.append(("앱", value))
            elif key == "target_nickname":
                visible.append(("대상 사용자", value))

        for key, value in {**query_values, **body_values}.items():
            if key in {"project_id", "application_id", "appDeploymentId", "app_deployment_name"}:
                continue
            if key == "name":
                visible.append(("이름", value))
            else:
                visible.append((key, value))
        return visible

    @staticmethod
    def _compose_plan_message(action: str, details: list[str]) -> str:
        if not details:
            return f"{action} 실행할까요?"
        return f"{', '.join(details)} 기준으로 {action} 실행할까요?"

    @staticmethod
    def _missing_input_intro(operation_id: str) -> str:
        intros = {
            "project.create": "프로젝트를 만들려면",
            "project.update_name": "프로젝트 이름을 바꾸려면",
            "project.update_resource": "프로젝트 리소스를 바꾸려면",
            "project.delete": "프로젝트를 삭제하려면",
            "project.add_member": "프로젝트 멤버를 추가하려면",
            "project.remove_member": "프로젝트 멤버를 제거하려면",
            "project.transfer_ownership": "프로젝트 소유권을 이전하려면",
            "application.create_apps": "애플리케이션을 만들려면",
            "application.delete_apps": "애플리케이션을 삭제하려면",
            "application.patch_apps_resources": "애플리케이션 리소스를 바꾸려면",
            "application.patch_apps_github": "애플리케이션 GitHub 연결 정보를 바꾸려면",
        }
        return intros.get(operation_id, "작업을 진행하려면")

    @staticmethod
    def _to_user_input_field(field_name: str) -> str:
        aliases = {
            "project_id": "project_name",
            "application_id": "application_name",
            "appDeploymentId": "application_name",
            "app_deployment_name": "application_name",
            "user_id": "target_nickname",
            "target_user_id": "target_nickname",
        }
        return aliases.get(field_name, field_name)

    @staticmethod
    def _normalize_input_name(field_name: Any) -> str:
        if isinstance(field_name, dict):
            return str(field_name.get("name", ""))
        return str(field_name)
