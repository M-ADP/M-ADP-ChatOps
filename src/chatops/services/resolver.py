from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from chatops.services.registry import RegistryEntry
from chatops.services.slots import (
    ApplicationResourceSlots,
    ApplicationCreateSlots,
    ApplicationGithubSlots,
    ApplicationReferenceSlots,
    MemberMutationSlots,
    MonitoringTrafficSlots,
    ProjectCreateSlots,
    ProjectReferenceSlots,
    ProjectResourceSlots,
    ProjectRenameSlots,
)
from chatops.services.user_matcher import match_user


KEY_VALUE_PATTERN = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?P<value>[^\s,}]+)")
JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
NAME_PATTERNS = (
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)"),
    re.compile(r"(?<![A-Za-z0-9._-])name\s*(?:은|는)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)", re.IGNORECASE),
)
NUMERIC_FIELD_PATTERNS = {
    "max_cpu": (
        re.compile(r"(?:max_cpu|cpu)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:개|코어)?", re.IGNORECASE),
    ),
    "max_memory": (
        re.compile(r"(?:max_memory|memory|메모리)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>기가|gb|GB|Gb|메가|mb|MB|Mb)?", re.IGNORECASE),
    ),
    "max_disk": (
        re.compile(r"(?:max_disk|disk|디스크)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>기가|gb|GB|Gb|테라|tb|TB|Tb)?", re.IGNORECASE),
    ),
    "cpu": (
        re.compile(r"(?:cpu)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:개|코어)?", re.IGNORECASE),
    ),
    "memory": (
        re.compile(r"(?:memory|메모리)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>기가|gb|GB|Gb|메가|mb|MB|Mb)?", re.IGNORECASE),
    ),
    "disk": (
        re.compile(r"(?:disk|디스크)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>기가|gb|GB|Gb|테라|tb|TB|Tb)?", re.IGNORECASE),
    ),
    "port": (
        re.compile(r"(?:port|포트)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+)", re.IGNORECASE),
    ),
}

# 한국어 숫자 → 아라비아 숫자 변환
KOREAN_NUMBER_MAP = {
    "하나": 1, "한": 1, "한 개": 1, "일": 1,
    "둘": 2, "두": 2, "두 개": 2, "이": 2,
    "셋": 3, "세": 3, "세 개": 3, "삼": 3,
    "넷": 4, "네": 4, "네 개": 4, "사": 4,
    "다섯": 5, "오": 5,
    "여섯": 6, "육": 6,
    "일곱": 7, "칠": 7,
    "여덟": 8, "팔": 8,
    "아홉": 9, "구": 9,
    "열": 10, "십": 10,
    "스물": 20, "이십": 20,
    "서른": 30, "삼십": 30,
    "백": 100,
}

KOREAN_CPU_PATTERN = re.compile(
    r"(?:cpu|max_cpu)\s*(?:은|는|이|가)?\s*(?P<value>한\s*개반|하나\s*반|하나|한|둘|두|셋|세|넷|다섯|여섯|일곱|여덟|아홉|열)\s*(?:개|코어)?",
    re.IGNORECASE,
)
RENAMED_NAME_PATTERNS = (
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)\s*로\s*(?:바꿔줘|바꿔|변경해줘|변경해|수정해줘|수정해|고쳐줘|고쳐)"),
)
PROJECT_NAME_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*프로젝트(?:에|를|을|은|는|이|가|\s|$)"),
)
APPLICATION_NAME_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*(?:앱|애플리케이션)(?:에|를|을|은|는|이|가|\s|$)"),
)
TARGET_NICKNAME_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*멤버\s*추가"),
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*멤버\s*(?:제거|삭제|지워)"),
    re.compile(r"소유권(?:을|은|는)?\s*(?P<value>[A-Za-z0-9._-]+)에게\s*(?:넘겨줘|넘겨|이전해줘|이전해)"),
    re.compile(r"(?:대상 사용자|닉네임)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)"),
)
TEXT_FIELD_PATTERNS = {
    "owner": (
        re.compile(r"(?:owner|깃허브 소유자|GitHub 소유자)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+)", re.IGNORECASE),
    ),
    "repository": (
        re.compile(r"(?:repository|repo|저장소 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+)", re.IGNORECASE),
    ),
    "branch": (
        re.compile(r"(?:branch|브랜치)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._/-]+)", re.IGNORECASE),
    ),
}

CLAUSE_SPLIT_PATTERN = re.compile(r"(?:,|\n|그리고|그런데|근데|하며|하고)")
TEXT_CORRECTION_PATTERNS = {
    "name": re.compile(r"(?:이름|name)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?:[A-Za-z0-9._/-]+)\s*(?:말고|아니고)\s*[\"']?(?P<value>[A-Za-z0-9._/-]+)", re.IGNORECASE),
    "owner": re.compile(r"(?:owner|깃허브 소유자|GitHub 소유자)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?:[A-Za-z0-9._/-]+)\s*(?:말고|아니고)\s*[\"']?(?P<value>[A-Za-z0-9._/-]+)", re.IGNORECASE),
    "repository": re.compile(r"(?:repository|repo|저장소 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?:[A-Za-z0-9._/-]+)\s*(?:말고|아니고)\s*[\"']?(?P<value>[A-Za-z0-9._/-]+)", re.IGNORECASE),
    "branch": re.compile(r"(?:branch|브랜치)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?:[A-Za-z0-9._/-]+)\s*(?:말고|아니고)\s*[\"']?(?P<value>[A-Za-z0-9._/-]+)", re.IGNORECASE),
}
NUMERIC_CORRECTION_PATTERNS = {
    "cpu": re.compile(r"(?:cpu|max_cpu)\s*(?:은|는|이|가|:|=)?\s*(?:\d+(?:\.\d+)?)\s*(?:말고|아니고)\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE),
    "memory": re.compile(r"(?:memory|메모리|max_memory)\s*(?:은|는|이|가|:|=)?\s*(?:\d+(?:\.\d+)?)\s*(?:기가|gb|GB|Gb|메가|mb|MB|Mb)?\s*(?:말고|아니고)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>기가|gb|GB|Gb|메가|mb|MB|Mb)?", re.IGNORECASE),
    "disk": re.compile(r"(?:disk|디스크|max_disk)\s*(?:은|는|이|가|:|=)?\s*(?:\d+(?:\.\d+)?)\s*(?:기가|gb|GB|Gb|테라|tb|TB|Tb)?\s*(?:말고|아니고)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>기가|gb|GB|Gb|테라|tb|TB|Tb)?", re.IGNORECASE),
    "port": re.compile(r"(?:port|포트)\s*(?:은|는|이|가|:|=)?\s*(?:\d+)\s*(?:말고|아니고)\s*(?P<value>\d+)", re.IGNORECASE),
}
PROJECT_REFERENCE_CORRECTION_PATTERN = re.compile(
    r"(?P<old>[A-Za-z0-9._-]+)\s*프로젝트\s*(?:말고|아니고)\s*(?P<value>[A-Za-z0-9._-]+)\s*프로젝트"
)
APPLICATION_REFERENCE_CORRECTION_PATTERN = re.compile(
    r"(?P<old>[A-Za-z0-9._-]+)\s*(?:앱|애플리케이션)\s*(?:말고|아니고)\s*(?P<value>[A-Za-z0-9._-]+)\s*(?:앱|애플리케이션)"
)

PROJECT_REFERENCE_OPERATION_IDS = {
    "project.delete",
    "project.get",
    "project.get_resource_limit",
    "project.list_members",
    "project.check_owner",
    "project.check_available",
    "application.get_apps",
}
APPLICATION_REFERENCE_OPERATION_IDS = {
    "application.delete_apps",
    "application.get_apps_status",
    "application.get_apps_logs",
    "application.get_apps_details",
}
APPLICATION_APP_NAME_QUERY_OPERATION_IDS = {
    "application.get_apps_status",
    "application.get_apps_logs",
    "application.get_apps_details",
}


class ParameterResolverService:
    def resolve(
        self,
        operation: RegistryEntry,
        message_text: str,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed_pairs = self._extract_pairs(message_text)
        references = self._extract_references(message_text)
        self._apply_session_context(message_text, parsed_pairs, references, session_context)
        self._apply_structured_corrections(message_text, parsed_pairs, references)
        self._apply_reference_aliases(operation, parsed_pairs, references)
        self._apply_time_range_aliases(operation, message_text, parsed_pairs)
        self._apply_typed_slot_models(operation.id, parsed_pairs, references)
        resolved: dict[str, Any] = {}

        path_values = self._resolve_named_fields(operation.required_inputs.get("path", []), parsed_pairs)
        if path_values:
            resolved["path"] = path_values

        query_values = self._resolve_named_fields(operation.required_inputs.get("query", []), parsed_pairs)
        if query_values:
            resolved["query"] = query_values

        body_spec = operation.required_inputs.get("body")
        if isinstance(body_spec, dict):
            body_values = self._resolve_body(body_spec, operation.important_inputs, parsed_pairs)
            if body_values:
                resolved["body"] = body_values

        if references:
            resolved["references"] = references

        remembered_ids = self._collect_resolved_ids_from_memory(references, session_context)
        if remembered_ids:
            resolved["resolved_ids"] = remembered_ids

        return resolved

    def _apply_typed_slot_models(
        self,
        operation_id: str,
        pairs: dict[str, Any],
        references: dict[str, Any],
    ) -> None:
        if operation_id in PROJECT_REFERENCE_OPERATION_IDS:
            slots = ProjectReferenceSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            return

        if operation_id == "project.create":
            slots = ProjectCreateSlots.model_validate(
                {
                    "name": pairs.get("name") or references.get("project_name"),
                    "max_cpu": pairs.get("max_cpu"),
                    "max_memory": pairs.get("max_memory"),
                    "max_disk": pairs.get("max_disk"),
                }
            )
            self._assign_if_present(pairs, "name", slots.name)
            self._assign_if_present(pairs, "max_cpu", slots.max_cpu)
            self._assign_if_present(pairs, "max_memory", slots.max_memory)
            self._assign_if_present(pairs, "max_disk", slots.max_disk)
            return

        if operation_id == "project.update_name":
            slots = ProjectRenameSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "name": pairs.get("name"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(pairs, "name", slots.name)
            return

        if operation_id == "project.update_resource":
            slots = ProjectResourceSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "max_cpu": pairs.get("max_cpu"),
                    "max_memory": pairs.get("max_memory"),
                    "max_disk": pairs.get("max_disk"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(pairs, "max_cpu", slots.max_cpu)
            self._assign_if_present(pairs, "max_memory", slots.max_memory)
            self._assign_if_present(pairs, "max_disk", slots.max_disk)
            return

        if operation_id in {"project.add_member", "project.remove_member", "project.transfer_ownership"}:
            slots = MemberMutationSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "target_nickname": references.get("target_nickname"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(references, "target_nickname", slots.target_nickname)
            return

        if operation_id == "application.create_apps":
            slots = ApplicationCreateSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "name": pairs.get("name") or references.get("application_name"),
                    "cpu": pairs.get("cpu"),
                    "memory": pairs.get("memory"),
                    "disk": pairs.get("disk"),
                    "port": pairs.get("port"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(pairs, "name", slots.name)
            self._assign_if_present(pairs, "cpu", slots.cpu)
            self._assign_if_present(pairs, "memory", slots.memory)
            self._assign_if_present(pairs, "disk", slots.disk)
            self._assign_if_present(pairs, "port", slots.port)
            return

        if operation_id in APPLICATION_REFERENCE_OPERATION_IDS:
            slots = ApplicationReferenceSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "application_name": references.get("application_name"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(references, "application_name", slots.application_name)
            return

        if operation_id == "application.patch_apps_github":
            slots = ApplicationGithubSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "application_name": references.get("application_name"),
                    "owner": pairs.get("owner"),
                    "repository": pairs.get("repository"),
                    "branch": pairs.get("branch"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(references, "application_name", slots.application_name)
            self._assign_if_present(pairs, "owner", slots.owner)
            self._assign_if_present(pairs, "repository", slots.repository)
            self._assign_if_present(pairs, "branch", slots.branch)
            return

        if operation_id == "application.patch_apps_resources":
            slots = ApplicationResourceSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "application_name": references.get("application_name"),
                    "max_cpu": pairs.get("max_cpu"),
                    "max_memory": pairs.get("max_memory"),
                    "max_disk": pairs.get("max_disk"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(references, "application_name", slots.application_name)
            self._assign_if_present(pairs, "max_cpu", slots.max_cpu)
            self._assign_if_present(pairs, "max_memory", slots.max_memory)
            self._assign_if_present(pairs, "max_disk", slots.max_disk)
            return

        if operation_id == "monitoring.get_app_deployment_traffic":
            slots = MonitoringTrafficSlots.model_validate(
                {
                    "project_name": references.get("project_name"),
                    "application_name": references.get("application_name"),
                    "start": pairs.get("start"),
                    "end": pairs.get("end"),
                }
            )
            self._assign_if_present(references, "project_name", slots.project_name)
            self._assign_if_present(references, "application_name", slots.application_name)
            if slots.start is not None:
                pairs["start"] = slots.start.isoformat()
            if slots.end is not None:
                pairs["end"] = slots.end.isoformat()

    def _extract_pairs(self, message_text: str) -> dict[str, Any]:
        pairs: dict[str, Any] = {}
        for match in KEY_VALUE_PATTERN.finditer(message_text):
            pairs[match.group("key")] = self._coerce(match.group("value"))

        loaded = None
        json_match = JSON_BLOCK_PATTERN.search(message_text)
        if json_match:
            try:
                loaded = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                loaded = None
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                pairs[str(key)] = value

        self._infer_natural_language_fields(message_text, pairs)
        return pairs

    def _apply_session_context(
        self,
        message_text: str,
        pairs: dict[str, Any],
        references: dict[str, Any],
        session_context: dict[str, Any] | None,
    ) -> None:
        if not session_context:
            return

        self._apply_entity_memory(message_text, references, session_context)

        # Entity memory: 이전 요청의 resolved references에서 엔티티를 가져옴
        last_refs = session_context.get("last_resolved_references")
        if isinstance(last_refs, dict) and self._should_use_entity_memory(message_text):
            for key in ("project_name", "application_name", "target_nickname"):
                if key not in references and key in last_refs:
                    references[key] = last_refs[key]

        if not self._should_use_session_context(message_text):
            return
        last_message_text = session_context.get("last_message_text")
        if not isinstance(last_message_text, str) or not last_message_text.strip():
            return
        fallback_pairs = self._extract_pairs(last_message_text)
        fallback_references = self._extract_references(last_message_text)
        if "name" not in pairs and "name" in fallback_pairs:
            pairs["name"] = fallback_pairs["name"]
        if "project_name" not in references and "project_name" in fallback_references:
            references["project_name"] = fallback_references["project_name"]
        if "application_name" not in references and "application_name" in fallback_references:
            references["application_name"] = fallback_references["application_name"]
        if "target_nickname" not in references and "target_nickname" in fallback_references:
            references["target_nickname"] = fallback_references["target_nickname"]

    def _apply_entity_memory(
        self,
        message_text: str,
        references: dict[str, Any],
        session_context: dict[str, Any],
    ) -> None:
        entity_memory = session_context.get("entity_memory")
        if not isinstance(entity_memory, dict):
            return

        projects = entity_memory.get("projects")
        applications = entity_memory.get("applications")
        users = entity_memory.get("users")

        if (
            "project_name" not in references
            and self._should_use_project_memory(message_text)
            and isinstance(projects, list)
        ):
            project_name = self._first_memory_name(projects)
            if project_name:
                references["project_name"] = project_name

        if (
            "application_name" not in references
            and self._should_use_application_memory(message_text)
            and isinstance(applications, list)
        ):
            application_name = self._first_memory_name(applications)
            if application_name:
                references["application_name"] = application_name
                if "project_name" not in references:
                    project_name = self._first_memory_project_name(applications)
                    if project_name:
                        references["project_name"] = project_name

        if (
            "target_nickname" not in references
            and self._should_use_user_memory(message_text)
            and isinstance(users, list)
        ):
            nickname = self._first_memory_name(users)
            if nickname:
                references["target_nickname"] = nickname
                if "project_name" not in references:
                    project_name = self._first_memory_project_name(users)
                    if project_name:
                        references["project_name"] = project_name

    def _should_use_session_context(self, message_text: str) -> bool:
        return any(marker in message_text for marker in ("그거", "그걸", "그거를", "아까", "방금", "이거"))

    def _should_use_entity_memory(self, message_text: str) -> bool:
        """엔티티 참조가 필요한 경우를 감지한다."""
        entity_ref_markers = (
            "그 프로젝트", "그 앱", "그 애플리케이션", "그 사람", "그 멤버",
            "방금 만든", "아까 만든", "방금 생성한", "아까 생성한",
            "그거", "그걸", "이거", "아까", "방금",
        )
        return any(marker in message_text for marker in entity_ref_markers)

    def _should_use_project_memory(self, message_text: str) -> bool:
        return any(marker in message_text for marker in ("그 프로젝트", "이 프로젝트", "방금 만든 프로젝트", "아까 만든 프로젝트"))

    def _should_use_application_memory(self, message_text: str) -> bool:
        return any(marker in message_text for marker in ("그 앱", "이 앱", "그 애플리케이션", "이 애플리케이션", "방금 만든 앱", "아까 만든 앱"))

    def _should_use_user_memory(self, message_text: str) -> bool:
        return any(marker in message_text for marker in ("그 사람", "이 사람", "그 멤버", "이 멤버", "방금 추가한 멤버", "아까 추가한 멤버"))

    def _collect_resolved_ids_from_memory(
        self,
        references: dict[str, Any],
        session_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not references or not session_context:
            return {}
        entity_memory = session_context.get("entity_memory")
        if not isinstance(entity_memory, dict):
            return {}

        resolved_ids: dict[str, Any] = {}
        project_name = references.get("project_name")
        application_name = references.get("application_name")
        target_nickname = references.get("target_nickname")

        project_entry = self._find_memory_entry(entity_memory.get("projects"), project_name)
        if project_entry and project_entry.get("resolved_id") is not None:
            resolved_ids["project_id"] = project_entry["resolved_id"]

        application_entry = self._find_memory_entry(
            entity_memory.get("applications"),
            application_name,
            project_name=project_name,
        )
        if application_entry:
            if application_entry.get("project_id") is not None and "project_id" not in resolved_ids:
                resolved_ids["project_id"] = application_entry["project_id"]
            if application_entry.get("resolved_id") is not None:
                resolved_ids["application_id"] = application_entry["resolved_id"]

        user_entry = self._find_memory_entry(
            entity_memory.get("users"),
            target_nickname,
            project_name=project_name,
            entity_type="user",
        )
        if user_entry:
            if user_entry.get("project_id") is not None and "project_id" not in resolved_ids:
                resolved_ids["project_id"] = user_entry["project_id"]
            if user_entry.get("resolved_id") is not None:
                resolved_ids["target_user_id"] = user_entry["resolved_id"]

        return resolved_ids

    @staticmethod
    def _first_memory_name(entries: list[Any]) -> str | None:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("canonical_name")
            if isinstance(name, str) and name:
                return name
        return None

    @staticmethod
    def _first_memory_project_name(entries: list[Any]) -> str | None:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            project_name = entry.get("project_name")
            if isinstance(project_name, str) and project_name:
                return project_name
        return None

    @staticmethod
    def _find_memory_entry(
        entries: Any,
        canonical_name: Any,
        *,
        project_name: Any = None,
        entity_type: str | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(entries, list) or not isinstance(canonical_name, str) or not canonical_name:
            return None
        if entity_type == "user":
            return match_user(canonical_name, entries, project_name=project_name).entry
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("canonical_name") != canonical_name:
                continue
            entry_project_name = entry.get("project_name")
            if project_name is not None and entry_project_name not in (None, project_name):
                continue
            return entry
        return None

    def _infer_natural_language_fields(self, message_text: str, pairs: dict[str, Any]) -> None:
        if "name" not in pairs:
            for pattern in (*RENAMED_NAME_PATTERNS, *NAME_PATTERNS):
                # Use last match so corrections override earlier values
                last_match = self._find_last_match(pattern, message_text)
                if last_match:
                    pairs["name"] = self._coerce(last_match.group("value"))
                    break
        # 한국어 숫자 CPU 표현 처리 (e.g. "cpu는 하나", "CPU는 두 개")
        self._infer_korean_numbers(message_text, pairs)

        for field_name, patterns in NUMERIC_FIELD_PATTERNS.items():
            if field_name in pairs:
                continue
            for pattern in patterns:
                last_match = self._find_last_match(pattern, message_text)
                if last_match:
                    value = self._coerce(last_match.group("value"))
                    # 단위 정규화
                    try:
                        unit = last_match.group("unit")
                    except IndexError:
                        unit = None
                    if unit:
                        value = self._normalize_unit(value, unit, field_name)
                    pairs[field_name] = value
                    break
        for field_name, patterns in TEXT_FIELD_PATTERNS.items():
            if field_name in pairs:
                continue
            for pattern in patterns:
                last_match = self._find_last_match(pattern, message_text)
                if last_match:
                    pairs[field_name] = self._coerce(last_match.group("value"))
                    break

    def _apply_structured_corrections(
        self,
        message_text: str,
        pairs: dict[str, Any],
        references: dict[str, Any],
    ) -> None:
        normalized = self._normalize_message_text(message_text)
        for clause in self._segment_clauses(normalized):
            self._apply_text_corrections(clause, pairs)
            self._apply_numeric_corrections(clause, pairs)
            self._apply_reference_corrections(clause, references)

    @staticmethod
    def _normalize_message_text(message_text: str) -> str:
        return re.sub(r"\s+", " ", message_text.strip())

    def _segment_clauses(self, message_text: str) -> list[str]:
        clauses = [segment.strip() for segment in CLAUSE_SPLIT_PATTERN.split(message_text) if segment.strip()]
        return clauses or [message_text]

    def _apply_text_corrections(self, clause: str, pairs: dict[str, Any]) -> None:
        for field_name, pattern in TEXT_CORRECTION_PATTERNS.items():
            match = pattern.search(clause)
            if not match:
                continue
            pairs[field_name] = self._coerce(match.group("value"))

    def _apply_numeric_corrections(self, clause: str, pairs: dict[str, Any]) -> None:
        alias_fields = {
            "cpu": "max_cpu",
            "memory": "max_memory",
            "disk": "max_disk",
        }
        for field_name, pattern in NUMERIC_CORRECTION_PATTERNS.items():
            match = pattern.search(clause)
            if not match:
                continue
            value = self._coerce(match.group("value"))
            try:
                unit = match.group("unit")
            except IndexError:
                unit = None
            if unit:
                value = self._normalize_unit(value, unit, field_name)
            pairs[field_name] = value
            alias_field = alias_fields.get(field_name)
            if alias_field is not None:
                pairs[alias_field] = value

    def _apply_reference_corrections(self, clause: str, references: dict[str, Any]) -> None:
        project_match = PROJECT_REFERENCE_CORRECTION_PATTERN.search(clause)
        if project_match:
            references["project_name"] = self._coerce(project_match.group("value"))
        app_match = APPLICATION_REFERENCE_CORRECTION_PATTERN.search(clause)
        if app_match:
            references["application_name"] = self._coerce(app_match.group("value"))

    def _infer_korean_numbers(self, message_text: str, pairs: dict[str, Any]) -> None:
        """한국어 숫자 표현을 처리한다 (e.g. 'cpu는 하나', 'CPU 하나 반')."""
        match = KOREAN_CPU_PATTERN.search(message_text)
        if match and "cpu" not in pairs and "max_cpu" not in pairs:
            raw = match.group("value").strip()
            if "반" in raw:
                # "하나 반" → 1.5, "한 개반" → 1.5
                base_str = raw.replace("반", "").replace("개", "").strip()
                base = KOREAN_NUMBER_MAP.get(base_str, 1)
                pairs["cpu"] = base + 0.5
            elif raw in KOREAN_NUMBER_MAP:
                pairs["cpu"] = KOREAN_NUMBER_MAP[raw]

    @staticmethod
    def _normalize_unit(value: Any, unit: str, field_name: str) -> Any:
        """단위를 정규화한다 (e.g. '1기가' → 1, '1024메가' → 1024)."""
        unit_lower = unit.lower()
        # 메모리/디스크 필드는 단위에 따라 변환하지 않음 (서버에서 기본 단위로 처리)
        # 단, 향후 필요 시 여기서 변환 가능
        return value

    @staticmethod
    def _find_last_match(pattern: re.Pattern, text: str):
        """Return the last match of a pattern in text, so corrections win over originals."""
        last = None
        for match in pattern.finditer(text):
            last = match
        return last

    def _extract_references(self, message_text: str) -> dict[str, Any]:
        references: dict[str, Any] = {}
        for pattern in PROJECT_NAME_PATTERNS:
            last_match = self._find_last_match(pattern, message_text)
            if last_match:
                references["project_name"] = self._coerce(last_match.group("value"))
                break
        for pattern in APPLICATION_NAME_PATTERNS:
            last_match = self._find_last_match(pattern, message_text)
            if last_match:
                references["application_name"] = self._coerce(last_match.group("value"))
                break
        for pattern in TARGET_NICKNAME_PATTERNS:
            last_match = self._find_last_match(pattern, message_text)
            if last_match:
                references["target_nickname"] = self._coerce(last_match.group("value"))
                break
        return references

    def _apply_reference_aliases(
        self,
        operation: RegistryEntry,
        pairs: dict[str, Any],
        references: dict[str, Any],
    ) -> None:
        operation_id = operation.id
        if operation_id == "project.create" and "name" not in pairs and "project_name" in references:
            pairs["name"] = references["project_name"]
        if operation_id == "project.create":
            if "cpu" in pairs and "max_cpu" not in pairs:
                pairs["max_cpu"] = pairs["cpu"]
            if "memory" in pairs and "max_memory" not in pairs:
                pairs["max_memory"] = pairs["memory"]
            if "disk" in pairs and "max_disk" not in pairs:
                pairs["max_disk"] = pairs["disk"]
        if operation_id.startswith("application.") and "name" not in pairs and "application_name" in references:
            pairs["name"] = references["application_name"]
        if operation_id in {"project.update_resource", "application.patch_apps_resources"}:
            if "cpu" in pairs and "max_cpu" not in pairs:
                pairs["max_cpu"] = pairs["cpu"]
            if "memory" in pairs and "max_memory" not in pairs:
                pairs["max_memory"] = pairs["memory"]
            if "disk" in pairs and "max_disk" not in pairs:
                pairs["max_disk"] = pairs["disk"]
        if operation_id in APPLICATION_APP_NAME_QUERY_OPERATION_IDS and "app_name" not in pairs:
            application_name = references.get("application_name")
            if application_name is not None:
                pairs["app_name"] = application_name
        if operation_id == "monitoring.get_app_deployment_traffic" and "app_deployment_name" not in pairs:
            application_name = references.get("application_name")
            if application_name is not None:
                pairs["app_deployment_name"] = application_name

    def _apply_time_range_aliases(
        self,
        operation: RegistryEntry,
        message_text: str,
        pairs: dict[str, Any],
    ) -> None:
        if operation.id != "monitoring.get_app_deployment_traffic":
            return
        time_range = self._extract_time_range(message_text)
        if not time_range:
            return
        pairs.update(time_range)

    def _extract_time_range(self, message_text: str) -> dict[str, str]:
        normalized = message_text.strip()
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst)
        explicit_range = self._extract_explicit_date_range(normalized, kst)
        if explicit_range:
            return explicit_range
        if "최근 1시간" in normalized or "지난 1시간" in normalized:
            start = now - timedelta(hours=1)
            return {"start": start.isoformat(), "end": now.isoformat()}
        if "최근 30분" in normalized or "지난 30분" in normalized:
            start = now - timedelta(minutes=30)
            return {"start": start.isoformat(), "end": now.isoformat()}
        if "최근 7일" in normalized or "지난 7일" in normalized or "최근 일주일" in normalized or "지난 일주일" in normalized:
            start = now - timedelta(days=7)
            return {"start": start.isoformat(), "end": now.isoformat()}
        if "어제" in normalized:
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
            return {"start": start.isoformat(), "end": end.isoformat()}
        if "오늘" in normalized:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return {"start": start.isoformat(), "end": now.isoformat()}
        return {}

    def _extract_explicit_date_range(self, message_text: str, tz: timezone) -> dict[str, str]:
        patterns = (
            re.compile(
                r"(?P<start>\d{4}[-/]\d{2}[-/]\d{2})\s*(?:부터|~|-)\s*(?P<end>\d{4}[-/]\d{2}[-/]\d{2})\s*(?:까지)?"
            ),
        )
        for pattern in patterns:
            match = pattern.search(message_text)
            if not match:
                continue
            start = self._coerce_date_string(match.group("start"), tz, end_of_day=False)
            end = self._coerce_date_string(match.group("end"), tz, end_of_day=True)
            if start and end:
                return {"start": start.isoformat(), "end": end.isoformat()}
        return {}

    @staticmethod
    def _coerce_date_string(raw: str, tz: timezone, *, end_of_day: bool) -> datetime | None:
        normalized = raw.replace("/", "-")
        try:
            parsed = datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError:
            return None
        if end_of_day:
            return parsed.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=tz)
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)

    def _resolve_named_fields(self, fields: list[dict[str, Any]], parsed_pairs: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for field in fields:
            field_name = str(field["name"])
            if field_name in parsed_pairs:
                resolved[field_name] = parsed_pairs[field_name]
        return resolved

    def _resolve_body(
        self,
        body_spec: dict[str, Any],
        important_inputs: dict[str, Any],
        parsed_pairs: dict[str, Any],
    ) -> dict[str, Any]:
        required_fields = body_spec.get("required_fields", [])
        important_body_fields = important_inputs.get("body", []) if isinstance(important_inputs, dict) else []
        candidate_fields = list(dict.fromkeys([*required_fields, *important_body_fields]))
        resolved: dict[str, Any] = {}
        for field_name in candidate_fields:
            if field_name in parsed_pairs:
                resolved[field_name] = parsed_pairs[field_name]
        return resolved

    @staticmethod
    def _assign_if_present(container: dict[str, Any], key: str, value: Any) -> None:
        if value is not None:
            container[key] = value

    def _coerce(self, value: str) -> Any:
        stripped = value.strip().strip("\"'")
        if re.fullmatch(r"-?\d+", stripped):
            return int(stripped)
        if re.fullmatch(r"-?\d+\.\d+", stripped):
            return float(stripped)
        return stripped
