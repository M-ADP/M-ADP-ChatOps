from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

import yaml


TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9_./-]+")
KEY_VALUE_PATTERN = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?P<value>[^\s,}]+)")
JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
NAME_HINT_PATTERNS = (
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)\s*로\s*(?:바꿔줘|바꿔|변경해줘|변경해|수정해줘|수정해|고쳐줘|고쳐)"),
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)"),
    re.compile(r"(?<![A-Za-z0-9._-])name\s*(?:은|는)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)", re.IGNORECASE),
)
PROJECT_ID_HINT_PATTERNS = (
    re.compile(r"(?:project_id|프로젝트\s*id|프로젝트ID)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+)", re.IGNORECASE),
    re.compile(r"프로젝트\s+(?P<value>\d+)(?:번)?\s*(?:을|를)?\s*(?:지워줘|지워|삭제해줘|삭제해|제거해줘|제거해|이름을|이름)\b"),
)
PROJECT_NAME_HINT_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*프로젝트(?:에|를|을|은|는|이|가|\s|$)"),
)
APPLICATION_NAME_HINT_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*(?:앱|애플리케이션)(?:에|를|을|은|는|이|가|\s|$)"),
)
TARGET_NICKNAME_HINT_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*멤버\s*추가"),
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*멤버\s*(?:제거|삭제|지워)"),
    re.compile(r"소유권(?:을|은|는)?\s*(?P<value>[A-Za-z0-9._-]+)에게\s*(?:넘겨줘|넘겨|이전해줘|이전해)"),
    re.compile(r"(?:대상 사용자|닉네임)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)"),
)
MODE_TO_KINDS = {
    "query": {"read"},
    "command": {"write", "delete", "action"},
}
KOREAN_SUFFIXES = ("해주세요", "해줘", "하세요", "해라", "하기", "해")
TOKEN_ALIASES = {
    "project": {"project", "프로젝트"},
    "프로젝트": {"project", "프로젝트"},
    "projects": {"project", "projects", "프로젝트"},
    "application": {"application", "app", "apps", "애플리케이션", "앱"},
    "app": {"application", "app", "apps", "애플리케이션", "앱"},
    "앱": {"application", "app", "apps", "애플리케이션", "앱"},
    "list": {"list", "목록", "리스트", "보여줘", "조회"},
    "목록": {"list", "목록", "리스트", "보여줘", "조회"},
    "리스트": {"list", "목록", "리스트", "보여줘", "조회"},
    "보여줘": {"list", "목록", "리스트", "보여줘", "조회"},
    "조회": {"list", "목록", "리스트", "보여줘", "조회"},
    "알려줘": {"list", "목록", "리스트", "보여줘", "조회", "알려줘"},
    "get": {"get", "조회", "상태", "보여줘"},
    "create": {"create", "생성", "만들어", "만들", "추가"},
    "생성": {"create", "생성", "만들어", "만들", "추가"},
    "delete": {"delete", "삭제", "제거", "지워"},
    "삭제": {"delete", "삭제", "제거", "지워"},
    "지워줘": {"delete", "삭제", "제거", "지워", "지워줘"},
    "지워": {"delete", "삭제", "제거", "지워", "지워줘"},
    "update": {"update", "수정", "변경", "업데이트"},
    "수정": {"update", "수정", "변경", "업데이트", "바꿔", "바꿔줘", "고쳐", "고쳐줘"},
    "변경": {"update", "수정", "변경", "업데이트", "바꿔", "바꿔줘", "고쳐", "고쳐줘"},
    "바꿔": {"update", "수정", "변경", "업데이트", "바꿔", "바꿔줘", "고쳐", "고쳐줘"},
    "바꿔줘": {"update", "수정", "변경", "업데이트", "바꿔", "바꿔줘", "고쳐", "고쳐줘"},
    "고쳐": {"update", "수정", "변경", "업데이트", "바꿔", "바꿔줘", "고쳐", "고쳐줘"},
    "고쳐줘": {"update", "수정", "변경", "업데이트", "바꿔", "바꿔줘", "고쳐", "고쳐줘"},
    "이름": {"name", "이름", "name"},
    "name": {"name", "이름", "name"},
    "member": {"member", "멤버", "구성원"},
    "members": {"member", "members", "멤버", "구성원"},
    "멤버": {"member", "members", "멤버", "구성원"},
    "소유권": {"owner", "소유권", "transfer", "ownership"},
    "넘겨줘": {"owner", "소유권", "transfer", "ownership"},
    "status": {"status", "상태"},
    "traffic": {"traffic", "트래픽"},
}


@dataclass(frozen=True)
class RegistryEntry:
    id: str
    source_file: str
    operation_id: str | None
    path: str
    method: str
    summary: str
    capability: str
    usable_in: tuple[str, ...]
    operation_kind: str
    when_to_use: tuple[str, ...]
    when_not_to_use: tuple[str, ...]
    requires_confirmation: bool
    risk_level: str
    side_effects: tuple[str, ...]
    required_headers: tuple[str, ...]
    enabled: bool = True
    required_inputs: dict[str, Any] = field(default_factory=dict)
    important_inputs: dict[str, Any] = field(default_factory=dict)
    preconditions: tuple[str, ...] = ()
    missing_info_questions: tuple[str, ...] = ()
    response_interpretation: str = ""
    plan_template: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegistryEntry":
        return cls(
            id=data["id"],
            source_file=data.get("source_file", ""),
            operation_id=data.get("operation_id"),
            path=data["path"],
            method=data["method"],
            summary=data.get("summary", ""),
            capability=data.get("capability", ""),
            usable_in=tuple(data.get("usable_in", [])),
            operation_kind=data["operation_kind"],
            when_to_use=tuple(data.get("when_to_use", [])),
            when_not_to_use=tuple(data.get("when_not_to_use", [])),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            risk_level=data.get("risk_level", "low"),
            enabled=bool(data.get("enabled", True)),
            side_effects=tuple(data.get("side_effects", [])),
            required_headers=tuple(data.get("required_headers", [])),
            required_inputs=data.get("required_inputs", {}),
            important_inputs=data.get("important_inputs", {}),
            preconditions=tuple(data.get("preconditions", [])),
            missing_info_questions=tuple(data.get("missing_info_questions", [])),
            response_interpretation=data.get("response_interpretation", ""),
            plan_template=tuple(data.get("plan_template", [])),
            examples=tuple(data.get("examples", [])),
        )

    def searchable_text(self) -> str:
        return " ".join(
            [
                self.id,
                self.path,
                self.method,
                self.summary,
                self.capability,
                *self.when_to_use,
                *self.examples,
            ]
        )


class RegistryService:
    def __init__(self, entries: list[RegistryEntry]) -> None:
        self.entries = tuple(entries)
        self.entries_by_id = {entry.id: entry for entry in self.entries}

    @classmethod
    def from_directory(cls, directory: str | Path) -> "RegistryService":
        root = Path(directory)
        entries = [
            RegistryEntry.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
            for path in sorted(root.glob("*.ai.yaml"))
        ]
        return cls(entries)

    def find_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[RegistryEntry]:
        filtered = [entry for entry in self.entries if self._matches_mode(entry, usable_in)]
        scored = sorted(
            filtered,
            key=lambda entry: (-self._score(entry, user_text), entry.id),
        )
        return scored[:limit]

    def get_entry(self, entry_id: str | None) -> RegistryEntry | None:
        if not entry_id:
            return None
        return self.entries_by_id.get(entry_id)

    def _matches_mode(self, entry: RegistryEntry, usable_in: str) -> bool:
        allowed_kinds = MODE_TO_KINDS.get(usable_in, set())
        if usable_in not in entry.usable_in:
            return False
        if not entry.enabled:
            return False
        if entry.operation_kind not in allowed_kinds:
            return False
        if usable_in == "query" and entry.requires_confirmation:
            return False
        return True

    def _score(self, entry: RegistryEntry, user_text: str) -> int:
        query_tokens = self._expand_tokens(self._tokenize(user_text))
        entry_tokens = self._expand_tokens(self._tokenize(entry.searchable_text()))
        id_tokens = self._expand_tokens(self._tokenize(entry.id))
        capability_tokens = self._expand_tokens(
            self._tokenize(" ".join([entry.summary, entry.capability, *entry.examples]))
        )
        supplied_fields = self._extract_supplied_fields(user_text)

        overlap = query_tokens & entry_tokens
        id_overlap = query_tokens & id_tokens
        capability_overlap = query_tokens & capability_tokens
        required_input_score = self._score_required_inputs(entry, supplied_fields)
        semantic_bonus = self._semantic_bonus(entry, user_text)
        return len(overlap) + (len(id_overlap) * 3) + (len(capability_overlap) * 2) + required_input_score + semantic_bonus

    def _semantic_bonus(self, entry: RegistryEntry, user_text: str) -> int:
        score = 0
        if self._is_member_list_request(user_text):
            if entry.id == "project.list_members":
                score += 18
            elif entry.id == "project.list_projects":
                score -= 4
        if self._is_member_add_request(user_text):
            if entry.id == "project.add_member":
                score += 24
            elif entry.id in {"project.create", "project.delete", "project.remove_member", "project.transfer_ownership"}:
                score -= 8
        if self._is_member_remove_request(user_text):
            if entry.id == "project.remove_member":
                score += 24
            elif entry.id in {"project.delete", "project.create", "project.add_member", "project.transfer_ownership"}:
                score -= 8
        if self._is_transfer_ownership_request(user_text):
            if entry.id == "project.transfer_ownership":
                score += 24
            elif entry.id in {"project.delete", "project.create", "project.add_member", "project.remove_member"}:
                score -= 8
        if self._is_resource_limit_request(user_text):
            if entry.id == "project.get_resource_limit":
                score += 18
            elif entry.id == "project.list_projects":
                score -= 4
        if self._is_owner_check_request(user_text):
            if entry.id == "project.check_owner":
                score += 18
        if self._is_available_check_request(user_text):
            if entry.id == "project.check_available":
                score += 18
        if self._is_project_detail_request(user_text):
            if entry.id == "project.get":
                score += 14
            elif entry.id == "project.list_projects":
                score -= 2
        if self._is_app_list_request(user_text):
            if entry.id == "application.get_apps":
                score += 18
            elif entry.id == "project.list_projects":
                score -= 4
        if self._is_app_status_request(user_text):
            if entry.id == "application.get_apps_status":
                score += 18
            elif entry.id == "monitoring.get_app_deployment_traffic":
                score -= 8
        if self._is_app_logs_request(user_text):
            if entry.id == "application.get_apps_logs":
                score += 18
            elif entry.id == "monitoring.get_app_deployment_traffic":
                score -= 8
        if self._is_app_details_request(user_text):
            if entry.id == "application.get_apps_details":
                score += 18
            elif entry.id == "monitoring.get_app_deployment_traffic":
                score -= 8
        if self._is_name_update_request(user_text):
            if entry.id == "project.update_name":
                score += 8
            elif "resource" in entry.id:
                score -= 4
        if self._is_resource_update_request(user_text):
            if entry.id == "project.update_resource":
                score += 14
            elif entry.id == "application.patch_apps_resources" and any(marker in user_text for marker in ("앱", "애플리케이션", "app")):
                score += 14
            elif entry.id in {"project.create", "project.update_name"}:
                score -= 6
            elif entry.operation_kind == "delete":
                score -= 10
        if self._is_create_request(user_text):
            has_project_context = "프로젝트" in user_text
            has_application_context = any(marker in user_text for marker in ("앱", "애플리케이션", "app"))
            if entry.id == "application.create_apps" and has_application_context:
                score += 12
            elif entry.id == "project.create" and has_project_context and not has_application_context:
                score += 12
            elif entry.operation_kind == "delete":
                score -= 8
            elif entry.id in {"application.patch_apps_github", "application.patch_apps_resources", "project.update_resource"}:
                score -= 4
        if self._is_delete_request(user_text) and entry.operation_kind == "delete":
            score += 6
            has_application_context = any(marker in user_text for marker in ("앱", "애플리케이션", "app"))
            if entry.id == "application.delete_apps" and has_application_context:
                score += 8
            if entry.id == "project.delete" and "프로젝트" in user_text:
                score += 4
            if entry.id == "project.delete" and has_application_context:
                score -= 10
        if self._is_github_update_request(user_text):
            if entry.id == "application.patch_apps_github":
                score += 16
            elif entry.operation_kind == "delete":
                score -= 8
        return score

    def _is_name_update_request(self, user_text: str) -> bool:
        return ("이름" in user_text or "name" in user_text.lower()) and any(
            marker in user_text for marker in ("바꿔", "변경", "수정", "고쳐")
        )

    def _is_delete_request(self, user_text: str) -> bool:
        return any(marker in user_text for marker in ("삭제", "제거", "지워"))

    def _is_create_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in lowered for marker in ("생성", "만들어", "만들", "추가", "create"))

    def _is_resource_update_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        resource_markers = ("리소스", "자원", "cpu", "메모리", "memory", "디스크", "disk")
        update_markers = ("늘려", "줄여", "변경", "수정", "조정", "업데이트", "update")
        return any(marker in lowered for marker in resource_markers) and any(
            marker in lowered for marker in update_markers
        )

    def _is_github_update_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        github_markers = ("깃허브", "github", "repository", "repo", "브랜치", "branch")
        update_markers = ("연결", "설정", "변경", "수정", "연동", "붙여")
        return any(marker in lowered for marker in github_markers) and any(
            marker in lowered for marker in update_markers
        )

    def _is_member_list_request(self, user_text: str) -> bool:
        return "멤버" in user_text and any(marker in user_text for marker in ("목록", "리스트", "보여", "조회"))

    def _is_member_add_request(self, user_text: str) -> bool:
        return "멤버" in user_text and any(marker in user_text for marker in ("추가", "넣어", "초대"))

    def _is_member_remove_request(self, user_text: str) -> bool:
        return "멤버" in user_text and any(marker in user_text for marker in ("제거", "삭제", "지워", "빼"))

    def _is_transfer_ownership_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in lowered for marker in ("소유권", "owner", "ownership")) and any(
            marker in lowered for marker in ("넘겨", "이전", "transfer")
        )

    def _is_resource_limit_request(self, user_text: str) -> bool:
        return "프로젝트" in user_text and "리소스" in user_text and any(marker in user_text for marker in ("한도", "제한"))

    def _is_owner_check_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return "프로젝트" in user_text and any(marker in lowered for marker in ("owner", "소유자"))

    def _is_available_check_request(self, user_text: str) -> bool:
        return "프로젝트" in user_text and any(marker in user_text for marker in ("접근 가능", "사용 가능", "가능한지", "가능해"))

    def _is_project_detail_request(self, user_text: str) -> bool:
        return "프로젝트" in user_text and any(marker in user_text for marker in ("상세", "자세히", "정보")) and "앱" not in user_text

    def _is_app_list_request(self, user_text: str) -> bool:
        return "프로젝트" in user_text and any(marker in user_text for marker in ("앱", "애플리케이션")) and any(
            marker in user_text for marker in ("목록", "리스트", "보여", "조회")
        )

    def _is_app_status_request(self, user_text: str) -> bool:
        return any(marker in user_text for marker in ("앱", "애플리케이션")) and "상태" in user_text

    def _is_app_logs_request(self, user_text: str) -> bool:
        return any(marker in user_text for marker in ("앱", "애플리케이션")) and "로그" in user_text

    def _is_app_details_request(self, user_text: str) -> bool:
        return any(marker in user_text for marker in ("앱", "애플리케이션")) and any(
            marker in user_text for marker in ("상세", "자세히", "정보")
        )

    def _tokenize(self, text: str) -> set[str]:
        return {token.lower() for token in TOKEN_PATTERN.findall(text) if token.strip()}

    def _expand_tokens(self, tokens: set[str]) -> set[str]:
        expanded = set(tokens)
        for token in list(tokens):
            expanded.update(token.split("."))
            expanded.update(token.split("_"))
            expanded.update(token.split("/"))
            expanded.update(token.split("-"))
            expanded.update(self._normalize_token(token))
        normalized = {token for token in expanded if token}
        aliases: set[str] = set(normalized)
        for token in normalized:
            aliases.update(TOKEN_ALIASES.get(token, set()))
        return aliases

    def _normalize_token(self, token: str) -> set[str]:
        normalized = {token}
        for suffix in KOREAN_SUFFIXES:
            if token.endswith(suffix) and len(token) > len(suffix):
                normalized.add(token[: -len(suffix)])
        return {item for item in normalized if item}

    def _extract_supplied_fields(self, user_text: str) -> set[str]:
        supplied_fields: set[str] = set()

        for match in KEY_VALUE_PATTERN.finditer(user_text):
            supplied_fields.add(match.group("key"))

        json_match = JSON_BLOCK_PATTERN.search(user_text)
        if json_match:
            try:
                loaded = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                supplied_fields.update(str(key) for key in loaded.keys())

        for pattern in NAME_HINT_PATTERNS:
            if pattern.search(user_text):
                supplied_fields.add("name")
                break
        for pattern in PROJECT_ID_HINT_PATTERNS:
            if pattern.search(user_text):
                supplied_fields.add("project_id")
                break
        for pattern in PROJECT_NAME_HINT_PATTERNS:
            if pattern.search(user_text):
                supplied_fields.add("project_name")
                break
        for pattern in APPLICATION_NAME_HINT_PATTERNS:
            if pattern.search(user_text):
                supplied_fields.add("application_name")
                break
        for pattern in TARGET_NICKNAME_HINT_PATTERNS:
            if pattern.search(user_text):
                supplied_fields.add("target_nickname")
                break
        return supplied_fields

    def _score_required_inputs(self, entry: RegistryEntry, supplied_fields: set[str]) -> int:
        score = 0
        required_inputs = entry.required_inputs
        required_field_names: set[str] = set()

        for field in required_inputs.get("path", []):
            field_name = str(field.get("name", ""))
            if field_name:
                required_field_names.add(field_name)
            if self._is_supplied(field_name, supplied_fields):
                score += 2
        for field in required_inputs.get("query", []):
            if not field.get("required", False):
                continue
            field_name = str(field.get("name", ""))
            if field_name:
                required_field_names.add(field_name)
            if self._is_supplied(field_name, supplied_fields):
                score += 2

        body_spec = required_inputs.get("body")
        if isinstance(body_spec, dict):
            for field_name in body_spec.get("required_fields", []):
                normalized = str(field_name)
                required_field_names.add(normalized)
                if self._is_supplied(normalized, supplied_fields):
                    score += 2

        if not required_field_names:
            return score + 2

        missing_required = {
            field_name
            for field_name in required_field_names
            if not self._is_supplied(field_name, supplied_fields)
        }
        score -= len(missing_required) * 2
        return score

    def _is_supplied(self, field_name: str, supplied_fields: set[str]) -> bool:
        aliases = {
            "project_id": {"project_id", "project_name"},
            "application_id": {"application_id", "application_name"},
            "app_deployment_name": {"app_deployment_name", "application_name"},
            "app_name": {"app_name", "application_name"},
            "user_id": {"user_id", "target_nickname"},
            "target_user_id": {"target_user_id", "target_nickname"},
        }
        accepted = aliases.get(field_name, {field_name})
        return any(alias in supplied_fields for alias in accepted)
