from __future__ import annotations

import asyncio
from typing import Any

from langgraph.types import interrupt

from chatops.domain.enums import RequestStatus
from chatops.graph.state import GraphState


class WorkflowNodes:
    def __init__(
        self,
        llm_service: Any,
        registry_service: Any,
        downstream_dispatcher: Any,
        resolver_service: Any,
    ) -> None:
        self.llm_service = llm_service
        self.registry_service = registry_service
        self.downstream_dispatcher = downstream_dispatcher
        self.resolver_service = resolver_service

    def ingest_request(self, state: GraphState) -> GraphState:
        effective_message_text = self._effective_message_text(state)
        return {
            "request_status": "processing",
            "requires_approval": False,
            "selected_operation_ids": [],
            "effective_message_text": effective_message_text,
        }

    def classify_request(self, state: GraphState) -> GraphState:
        classification = self.llm_service.classify(state.get("effective_message_text", state["message_text"]))
        return {
            "request_type": str(classification["request_type"]),
            "intent": str(classification.get("intent", "")),
            "classification_reason": str(classification.get("classification_reason", "")),
            "classification_confidence": float(classification.get("classification_confidence", 0.0)),
        }

    def route_request(self, state: GraphState) -> GraphState:
        return {"route": state["request_type"]}

    def answer_inquiry(self, state: GraphState) -> GraphState:
        return {
            "final_response": self.llm_service.answer_inquiry(state["message_text"]),
            "request_status": "completed",
            "requires_approval": False,
        }

    def prepare_query(self, state: GraphState) -> GraphState:
        candidates = self.registry_service.find_candidates(state.get("effective_message_text", state["message_text"]), usable_in="query")
        selected = candidates[0] if candidates else None
        return {
            "selected_operation_id": selected.id if selected is not None else None,
            "selected_operation_ids": [candidate.id for candidate in candidates],
        }

    def execute_query(self, state: GraphState) -> GraphState:
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        if operation is None:
            return {
                "query_result": {"summary": "적절한 조회 API를 찾지 못했습니다."},
            }

        resolved_inputs = self.resolver_service.resolve(
            operation,
            state.get("effective_message_text", state["message_text"]),
            session_context=state.get("session_context"),
        )
        return {
            "resolved_inputs": resolved_inputs,
            "query_result": self._run_awaitable(
                self.downstream_dispatcher.execute_query(
                    operation,
                    state["user_id"],
                    user_role=state.get("user_role"),
                    org_id=state.get("org_id"),
                    resolved_inputs=resolved_inputs,
                )
            ),
        }

    def interpret_result(self, state: GraphState) -> GraphState:
        raw_result = state.get("query_result") or {}
        return {
            "final_response": self.llm_service.interpret_query_result(
                state["message_text"],
                raw_result,
            ),
            "request_status": "completed",
            "requires_approval": False,
        }

    def plan_command(self, state: GraphState) -> GraphState:
        effective_message_text = state.get("effective_message_text", state["message_text"])
        candidates = self.registry_service.find_candidates(effective_message_text, usable_in="command")
        operation_ids = [candidate.id for candidate in candidates]
        selected = candidates[0] if candidates else None
        if selected is None:
            return {
                "selected_operation_id": None,
                "selected_operation_ids": operation_ids,
                "final_response": "적절한 명령 API를 찾지 못했습니다.",
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
            }

        resolved_inputs = self.resolver_service.resolve(
            selected,
            effective_message_text,
            session_context=state.get("session_context"),
        )
        missing_inputs = self._missing_required_inputs(selected, resolved_inputs)
        if missing_inputs:
            return {
                "selected_operation_id": selected.id,
                "selected_operation_ids": operation_ids,
                "resolved_inputs": resolved_inputs,
                "missing_inputs": missing_inputs,
                "final_response": self._format_missing_input_response(selected, missing_inputs),
                "request_status": RequestStatus.INPUT_REQUIRED.value,
                "requires_approval": False,
            }
        return {
            "selected_operation_id": selected.id,
            "selected_operation_ids": operation_ids,
            "resolved_inputs": resolved_inputs,
            "final_response": self._build_command_plan(selected, resolved_inputs),
            "request_status": RequestStatus.PENDING_APPROVAL.value,
            "requires_approval": True,
        }

    def wait_for_approval(self, state: GraphState) -> GraphState:
        approved = interrupt(
            {
                "request_id": state["request_id"],
                "session_id": state["session_id"],
                "plan": state.get("final_response"),
                "selected_operation_ids": list(state.get("selected_operation_ids", [])),
            }
        )
        return {
            "approval_granted": bool(approved),
            "request_status": "approved" if approved else "rejected",
            "requires_approval": False,
            "final_response": state.get("final_response") if approved else "명령 실행이 거절되었습니다.",
        }

    def execute_command(self, state: GraphState) -> GraphState:
        operation_id = state.get("selected_operation_id")
        operation = self.registry_service.get_entry(operation_id) if operation_id else None
        if operation is None:
            return {
                "command_result": {"success": False, "summary": "적절한 명령 API를 찾지 못했습니다."},
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
            }

        resolved_inputs = state.get("resolved_inputs") or self.resolver_service.resolve(
            operation,
            state.get("effective_message_text", state["message_text"]),
            session_context=state.get("session_context"),
        )
        return {
            "resolved_inputs": resolved_inputs,
            "command_result": self._run_awaitable(
                self.downstream_dispatcher.execute_command(
                    operation,
                    state["user_id"],
                    user_role=state.get("user_role"),
                    org_id=state.get("org_id"),
                    resolved_inputs=resolved_inputs,
                )
            ),
            "request_status": RequestStatus.EXECUTING.value,
            "requires_approval": False,
        }

    def respond_command(self, state: GraphState) -> GraphState:
        result = state.get("command_result") or {}
        summary = str(result.get("summary", "명령 실행 결과가 없습니다."))
        operation_id = str(state.get("selected_operation_id") or "")
        if result.get("success") is False:
            return {
                "final_response": self._build_command_failure_message(operation_id, summary),
                "request_status": RequestStatus.FAILED.value,
                "requires_approval": False,
            }
        return {
            "final_response": self._build_command_success_message(operation_id, summary),
            "request_status": RequestStatus.COMPLETED.value,
            "requires_approval": False,
        }

    def _missing_required_inputs(self, operation, resolved_inputs: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        required_inputs = operation.required_inputs
        important_inputs = operation.important_inputs or {}
        path_values = resolved_inputs.get("path", {})
        query_values = resolved_inputs.get("query", {})
        body_values = resolved_inputs.get("body", {})
        references = resolved_inputs.get("references", {})

        for field in required_inputs.get("path", []):
            field_name = str(field.get("name", ""))
            if not field.get("required", True) or not field_name:
                continue
            if field_name in path_values or self._is_reference_satisfied(field_name, references):
                continue
            missing.append(self._to_user_input_field(field_name))

        for field in required_inputs.get("query", []):
            field_name = str(field.get("name", ""))
            if not field.get("required", False) or not field_name:
                continue
            if field_name in query_values or self._is_reference_satisfied(field_name, references):
                continue
            missing.append(self._to_user_input_field(field_name))

        body_spec = required_inputs.get("body")
        if isinstance(body_spec, dict):
            for field_name in body_spec.get("required_fields", []):
                normalized = str(field_name)
                if normalized in body_values or self._is_reference_satisfied(normalized, references):
                    continue
                missing.append(self._to_user_input_field(normalized))

        for field_name in important_inputs.get("path", []):
            normalized = str(field_name)
            if normalized in path_values or self._is_reference_satisfied(normalized, references):
                continue
            missing.append(self._to_user_input_field(normalized))

        for field_name in important_inputs.get("query", []):
            normalized = str(field_name)
            if normalized in query_values or self._is_reference_satisfied(normalized, references):
                continue
            missing.append(self._to_user_input_field(normalized))

        for field_name in important_inputs.get("body", []):
            normalized = str(field_name)
            if normalized in body_values or self._is_reference_satisfied(normalized, references):
                continue
            missing.append(self._to_user_input_field(normalized))

        return list(dict.fromkeys(missing))

    def _effective_message_text(self, state: GraphState) -> str:
        message_text = state["message_text"]
        session_context = state.get("session_context") or {}
        if not self._should_continue_previous_request(message_text, session_context):
            return message_text

        last_effective_message_text = session_context.get("last_effective_message_text")
        if isinstance(last_effective_message_text, str) and last_effective_message_text.strip():
            return f"{last_effective_message_text}\n{message_text}".strip()

        last_message_text = session_context.get("last_message_text")
        if not isinstance(last_message_text, str) or not last_message_text.strip():
            return message_text
        return f"{last_message_text}\n{message_text}".strip()

    def _should_continue_previous_request(self, message_text: str, session_context: dict[str, Any]) -> bool:
        if session_context.get("last_request_status") != RequestStatus.INPUT_REQUIRED.value:
            return False
        if not isinstance(message_text, str) or not message_text.strip():
            return False

        supplement_markers = (
            "이름",
            "프로젝트 이름",
            "앱 이름",
            "애플리케이션 이름",
            "cpu",
            "max_cpu",
            "memory",
            "메모리",
            "max_memory",
            "disk",
            "디스크",
            "max_disk",
            "port",
            "포트",
            "owner",
            "repository",
            "repo",
            "branch",
            "브랜치",
            "깃허브",
            "github",
            "=",
            ":",
            "그거",
            "이거",
            "아까",
            "방금",
            "닉네임",
            "대상 사용자",
            "멤버",
            "소유권",
        )
        return any(marker in message_text for marker in supplement_markers)

    def _format_missing_input_response(self, operation, missing_inputs: list[str]) -> str:
        labels = [self._format_missing_input_prompt_label(operation.id, field_name) for field_name in missing_inputs]
        joined_labels = ", ".join(labels)
        return f"{self._missing_input_intro(operation.id)} 아래 정보가 더 필요합니다. {joined_labels}를 알려주세요."

    def _format_missing_input_label(self, field_name: str) -> str:
        labels = {
            "name": "이름(name)",
            "project_name": "대상 프로젝트",
            "application_name": "앱 이름",
            "application_id": "앱 이름",
            "appDeploymentId": "앱 이름",
            "target_nickname": "대상 사용자 닉네임",
            "cpu": "CPU(cpu)",
            "max_cpu": "최대 CPU(max_cpu)",
            "memory": "메모리(memory)",
            "max_memory": "최대 메모리(max_memory)",
            "disk": "디스크(disk)",
            "max_disk": "최대 디스크(max_disk)",
            "port": "포트(port)",
            "owner": "GitHub 소유자(owner)",
            "repository": "저장소 이름(repository)",
            "branch": "브랜치(branch)",
        }
        return labels.get(field_name, field_name)

    def _format_missing_input_prompt_label(self, operation_id: str, field_name: str) -> str:
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

    def _format_missing_input_example(self, field_name: str) -> str:
        examples = {
            "name": "name=demo 또는 '이름은 demo야'",
            "project_name": "'demo 프로젝트' 또는 '대상 프로젝트는 demo야'",
            "application_name": "'api-server 앱' 또는 '앱 이름은 api-server야'",
            "application_id": "'api-server 앱' 또는 '앱 이름은 api-server야'",
            "appDeploymentId": "'api-server 앱' 또는 '앱 이름은 api-server야'",
            "target_nickname": "'alice 멤버 추가해줘' 또는 '닉네임은 alice야'",
            "cpu": "cpu=0.5",
            "max_cpu": "max_cpu=1 또는 'cpu는 1이야'",
            "memory": "memory=0.5",
            "max_memory": "max_memory=0.5 또는 '메모리는 0.5야'",
            "disk": "disk=10",
            "max_disk": "max_disk=10 또는 '디스크는 10이야'",
            "port": "port=8080",
            "owner": "owner=M-ADP 또는 'GitHub 소유자는 M-ADP야'",
            "repository": "repository=my-repo 또는 '저장소 이름은 my-repo야'",
            "branch": "branch=main 또는 '브랜치는 main이야'",
        }
        return examples.get(field_name, "")

    def _build_command_plan(self, operation, resolved_inputs: dict[str, Any]) -> str:
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

    def _compose_plan_message(self, action: str, details: list[str]) -> str:
        if not details:
            return f"{action} 실행할까요?"
        return f"{', '.join(details)} 기준으로 {action} 실행할까요?"

    def _missing_input_intro(self, operation_id: str) -> str:
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

    def _build_command_success_message(self, operation_id: str, summary: str) -> str:
        messages = {
            "project.create": "프로젝트를 생성했습니다.",
            "project.update_name": "프로젝트 이름을 변경했습니다.",
            "project.update_resource": "프로젝트 리소스를 변경했습니다.",
            "project.delete": "프로젝트를 삭제했습니다.",
            "project.add_member": "프로젝트 멤버를 추가했습니다.",
            "project.remove_member": "프로젝트 멤버를 제거했습니다.",
            "project.transfer_ownership": "프로젝트 소유권을 이전했습니다.",
            "application.create_apps": "애플리케이션을 생성했습니다.",
            "application.delete_apps": "애플리케이션을 삭제했습니다.",
            "application.patch_apps_resources": "애플리케이션 자원을 변경했습니다.",
            "application.patch_apps_github": "애플리케이션 GitHub 연결 정보를 변경했습니다.",
        }
        return messages.get(operation_id, f"요청한 작업을 완료했습니다. {summary}")

    def _build_command_failure_message(self, operation_id: str, summary: str) -> str:
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
        return f"{subject}에 실패했습니다. {summary}"

    def _is_reference_satisfied(self, field_name: str, references: dict[str, Any]) -> bool:
        reference_aliases = {
            "project_id": "project_name",
            "application_id": "application_name",
            "appDeploymentId": "application_name",
            "app_deployment_name": "application_name",
            "user_id": "target_nickname",
            "target_user_id": "target_nickname",
        }
        alias = reference_aliases.get(field_name)
        return bool(alias and references.get(alias))

    def _to_user_input_field(self, field_name: str) -> str:
        aliases = {
            "project_id": "project_name",
            "application_id": "application_name",
            "appDeploymentId": "application_name",
            "app_deployment_name": "application_name",
            "user_id": "target_nickname",
            "target_user_id": "target_nickname",
        }
        return aliases.get(field_name, field_name)

    def _run_awaitable(self, awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("async downstream 호출은 현재 sync workflow에서만 지원합니다.")
