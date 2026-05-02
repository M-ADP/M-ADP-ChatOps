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
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름|어플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)\s*로\s*(?:바꿔줘|바꿔|변경해줘|변경해|수정해줘|수정해|고쳐줘|고쳐)"),
    re.compile(r"(?:이름|프로젝트명|프로젝트 이름|앱 이름|애플리케이션 이름|어플리케이션 이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)"),
    re.compile(r"(?<![A-Za-z0-9._-])name\s*(?:은|는)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+?)(?:야|이야|입니다|이에요|예요)?(?:[.!?,\s]|$)", re.IGNORECASE),
)
PROJECT_ID_HINT_PATTERNS = (
    re.compile(r"(?:project_id|프로젝트\s*id|프로젝트ID)\s*(?:은|는|이|가|:|=)?\s*(?P<value>\d+)", re.IGNORECASE),
    re.compile(r"프로젝트\s+(?P<value>\d+)(?:번)?\s*(?:을|를)?\s*(?:지워줘|지워|삭제해줘|삭제해|제거해줘|제거해|이름을|이름)\b"),
)
PROJECT_NAME_HINT_PATTERNS = (
    re.compile(r"(?:대상\s+프로젝트|프로젝트명|프로젝트\s+이름)\s*(?:은|는|이|가|:|=)?\s*[\"']?(?P<value>[A-Za-z0-9._-]+)(?:[.!?,\s]|$)"),
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*프로젝트(?:에|를|을|은|는|이|가|\s|$)"),
)
APPLICATION_NAME_HINT_PATTERNS = (
    re.compile(r"(?P<value>[A-Za-z0-9._-]+)\s*(?:앱|애플리케이션|어플리케이션)(?:에|를|을|은|는|이|가|\s|$)"),
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
    "application": {"application", "app", "apps", "애플리케이션", "어플리케이션", "앱"},
    "app": {"application", "app", "apps", "애플리케이션", "어플리케이션", "앱"},
    "앱": {"application", "app", "apps", "애플리케이션", "어플리케이션", "앱"},
    "애플리케이션": {"application", "app", "apps", "애플리케이션", "어플리케이션", "앱"},
    "어플리케이션": {"application", "app", "apps", "애플리케이션", "어플리케이션", "앱"},
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
    timeout_seconds: int = 30

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
            timeout_seconds=int(data.get("timeout_seconds", 30)),
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


@dataclass(frozen=True)
class ScoredCandidate:
    """점수가 매겨진 후보 오퍼레이션."""
    entry: RegistryEntry
    score: int


class RegistryService:
    def __init__(
        self,
        entries: list[RegistryEntry],
        minimum_score_threshold: int = 8,
        ambiguity_score_threshold: int = 5,
        semantic_router: Any = None,
    ) -> None:
        self.entries = tuple(entries)
        self.entries_by_id = {entry.id: entry for entry in self.entries}
        self.minimum_score_threshold = minimum_score_threshold
        self.ambiguity_score_threshold = ambiguity_score_threshold
        self._semantic_router = semantic_router

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        minimum_score_threshold: int = 8,
        ambiguity_score_threshold: int = 5,
        use_semantic_router: bool = True,
    ) -> "RegistryService":
        root = Path(directory)
        entries = [
            RegistryEntry.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
            for path in sorted(root.glob("*.ai.yaml"))
        ]
        router = None
        if use_semantic_router:
            try:
                from chatops.services.semantic_router import SemanticRouter
            except ImportError:
                from src.chatops.services.semantic_router import SemanticRouter  # type: ignore[no-redef]
            router = SemanticRouter.from_registry(entries)
        return cls(
            entries,
            minimum_score_threshold=minimum_score_threshold,
            ambiguity_score_threshold=ambiguity_score_threshold,
            semantic_router=router,
        )

    # Agent가 쓰기 작업 전에 항상 호출해야 하는 precheck 도구.
    # 사용자 쿼리 텍스트에 관련 키워드가 없어도 점수를 못 받으므로 항상 포함한다.
    _ALWAYS_INCLUDED_AGENT_TOOLS: frozenset[str] = frozenset({"project.check_available"})

    def find_agent_candidates(self, user_text: str, limit: int = 8) -> list[RegistryEntry]:
        """Agent Loop용 도구 후보 필터링.

        SemanticRouter 사용 가능 시: 코사인 유사도 기반으로 limit개까지 필터링.
        미사용 시(keyword fallback): 전체 enabled entries 반환 (필터 효과 미미하므로).
        두 경우 모두 _ALWAYS_INCLUDED_AGENT_TOOLS는 항상 포함한다.
        """
        all_enabled = list(self.all_enabled_entries())

        if self._semantic_router is None:
            return all_enabled

        user_vec = self._semantic_router.embed_text(user_text) if user_text.strip() else None
        if user_vec is None:
            return all_enabled

        scored = sorted(
            [(entry, self._score(entry, user_text, user_vec=user_vec)) for entry in all_enabled],
            key=lambda pair: (-pair[1], pair[0].id),
        )
        candidates = [entry for entry, score in scored if score >= self.minimum_score_threshold][:limit]

        # 항상 포함해야 하는 도구가 candidates에 없으면 추가
        candidate_ids = {e.id for e in candidates}
        for tool_id in self._ALWAYS_INCLUDED_AGENT_TOOLS:
            if tool_id not in candidate_ids and tool_id in self.entries_by_id:
                candidates.append(self.entries_by_id[tool_id])

        return candidates if candidates else all_enabled

    def find_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[RegistryEntry]:
        """점수 기준으로 후보를 반환한다. threshold 미달 후보는 제외."""
        scored = self.find_scored_candidates(user_text, usable_in, limit)
        return [sc.entry for sc in scored]

    def find_scored_candidates(
        self, user_text: str, usable_in: str, limit: int = 5,
    ) -> list[ScoredCandidate]:
        """P1: threshold 적용 + 점수 포함 후보 반환."""
        filtered = [entry for entry in self.entries if self._matches_mode(entry, usable_in)]
        # user_text 임베딩은 entry 순회 전에 1회만 계산한다
        user_vec = self._semantic_router.embed_text(user_text) if self._semantic_router else None
        scored = sorted(
            [(entry, self._score(entry, user_text, user_vec=user_vec)) for entry in filtered],
            key=lambda pair: (-pair[1], pair[0].id),
        )
        above_threshold = [
            ScoredCandidate(entry=entry, score=score)
            for entry, score in scored
            if score >= self.minimum_score_threshold
        ]
        return above_threshold[:limit]

    def detect_ambiguity(
        self, scored_candidates: list[ScoredCandidate],
    ) -> tuple[bool, list[ScoredCandidate]]:
        """P0: 상위 후보 간 점수 차이가 작으면 모호한 것으로 판단.

        Returns:
            (is_ambiguous, ambiguous_candidates)
        """
        if len(scored_candidates) < 2:
            return False, []
        top = scored_candidates[0]
        second = scored_candidates[1]
        # 서로 다른 도메인(project vs application 등)이면서 점수 차이가 작은 경우만 모호
        top_domain = top.entry.id.split(".")[0]
        second_domain = second.entry.id.split(".")[0]
        if top_domain == second_domain:
            return False, []
        score_gap = top.score - second.score
        if score_gap <= self.ambiguity_score_threshold:
            return True, [top, second]
        return False, []

    def all_enabled_entries(self) -> list[RegistryEntry]:
        """활성화된 모든 엔트리를 반환한다 (Agent Loop 도구 스키마 생성용)."""
        return [entry for entry in self.entries if entry.enabled]

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

    def _score(self, entry: RegistryEntry, user_text: str, user_vec: list[float] | None = None) -> int:
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
        semantic_bonus = self._semantic_bonus(entry, user_text, user_vec=user_vec)
        return len(overlap) + (len(id_overlap) * 3) + (len(capability_overlap) * 2) + required_input_score + semantic_bonus

    def _semantic_bonus(self, entry: RegistryEntry, user_text: str, user_vec: list[float] | None = None) -> int:
        """Positive bonus는 SemanticRouter 사용 시 임베딩 기반, 미사용 시 keyword fallback."""
        score = 0
        if self._semantic_router is not None and user_vec is not None:
            score += self._semantic_router.score_bonus(user_vec, entry.id)
        else:
            score += self._keyword_positive_bonus(entry, user_text)
        score += self._keyword_negative_penalty(entry, user_text)
        return score

    def _keyword_positive_bonus(self, entry: RegistryEntry, user_text: str) -> int:
        """키워드 기반 positive bonus (SemanticRouter 미사용 시 fallback)."""
        score = 0
        if self._is_invitation_list_request(user_text):
            if entry.id == "project.list_member_invitations":
                score += 24
        if self._is_member_list_request(user_text):
            if entry.id == "project.list_members":
                score += 18
        if self._is_member_add_request(user_text):
            if entry.id == "project.invite_member":
                score += 24
        if self._is_member_remove_request(user_text):
            if entry.id == "project.remove_member":
                score += 24
        if self._is_transfer_ownership_request(user_text):
            if entry.id == "project.transfer_ownership":
                score += 24
        if self._is_resource_limit_request(user_text):
            if entry.id == "project.get_resource_limit":
                score += 18
        if self._is_project_list_request(user_text):
            if entry.id == "project.list_projects":
                score += 12
        if self._is_owner_check_request(user_text):
            if entry.id == "project.check_owner":
                score += 18
        if self._is_available_check_request(user_text):
            if entry.id == "project.check_available":
                score += 18
        if self._is_project_detail_request(user_text):
            if entry.id == "project.get":
                score += 14
        if self._is_app_list_request(user_text):
            if entry.id == "application.get_apps":
                score += 18
        if self._is_app_status_request(user_text):
            if entry.id == "application.get_apps_status":
                score += 18
        if self._is_app_logs_request(user_text):
            if entry.id == "application.get_apps_logs":
                score += 18
        if self._is_app_details_request(user_text):
            if entry.id == "application.get_apps_details":
                score += 18
        if self._is_name_update_request(user_text):
            if entry.id == "project.update_name":
                score += 8
        if self._is_resource_update_request(user_text):
            if entry.id == "project.update_resource":
                score += 14
            elif entry.id == "application.patch_apps_resources" and self._has_application_context(user_text):
                score += 14
        if self._is_create_request(user_text):
            has_project_context = self._has_project_context(user_text)
            has_application_context = self._has_application_context(user_text)
            if entry.id == "application.create_apps" and has_application_context:
                score += 12
            elif entry.id == "project.create" and has_project_context and not has_application_context:
                score += 12
        if self._is_delete_request(user_text) and entry.operation_kind == "delete":
            score += 6
            has_application_context = self._has_application_context(user_text)
            if entry.id == "application.delete_apps" and has_application_context:
                score += 8
            if entry.id == "project.delete" and self._has_project_context(user_text):
                score += 4
        if self._is_github_update_request(user_text):
            if entry.id == "application.patch_apps_github":
                score += 16
        return score

    def _keyword_negative_penalty(self, entry: RegistryEntry, user_text: str) -> int:
        """키워드 기반 negative penalty (SemanticRouter 사용 여부와 무관하게 항상 적용)."""
        score = 0
        if self._is_invitation_list_request(user_text):
            if entry.id in {"project.list_members", "project.list_projects"}:
                score -= 4
        if self._is_member_list_request(user_text):
            if entry.id == "project.list_projects":
                score -= 4
        if self._is_member_add_request(user_text):
            if entry.id in {"project.create", "project.delete", "project.remove_member", "project.transfer_ownership"}:
                score -= 8
        if self._is_member_remove_request(user_text):
            if entry.id in {"project.delete", "project.create", "project.invite_member", "project.transfer_ownership"}:
                score -= 8
        if self._is_transfer_ownership_request(user_text):
            if entry.id in {"project.delete", "project.create", "project.invite_member", "project.remove_member"}:
                score -= 8
        if self._is_resource_limit_request(user_text):
            if entry.id == "project.list_projects":
                score -= 4
        if self._is_project_list_request(user_text):
            if entry.id == "project.get":
                score -= 8
        if self._is_project_detail_request(user_text):
            if entry.id == "project.list_projects":
                score -= 2
        if self._is_app_list_request(user_text):
            if entry.id == "project.list_projects":
                score -= 4
        if self._is_app_status_request(user_text):
            if entry.id == "monitoring.get_app_deployment_traffic":
                score -= 8
        if self._is_app_logs_request(user_text):
            if entry.id == "monitoring.get_app_deployment_traffic":
                score -= 8
        if self._is_app_details_request(user_text):
            if entry.id == "monitoring.get_app_deployment_traffic":
                score -= 8
        if self._is_name_update_request(user_text):
            if "resource" in entry.id:
                score -= 4
        if self._is_resource_update_request(user_text):
            if entry.id in {"project.create", "project.update_name"}:
                score -= 6
            elif entry.operation_kind == "delete":
                score -= 10
        if self._is_create_request(user_text):
            has_application_context = self._has_application_context(user_text)
            if entry.id == "project.create" and has_application_context:
                score -= 12
            elif entry.operation_kind == "delete":
                score -= 8
            elif entry.id in {"application.patch_apps_github", "application.patch_apps_resources", "project.update_resource"}:
                score -= 4
        if self._is_delete_request(user_text) and entry.operation_kind == "delete":
            if entry.id == "project.delete" and self._has_application_context(user_text):
                score -= 10
        if self._is_github_update_request(user_text):
            if entry.operation_kind == "delete":
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

    def _is_invitation_list_request(self, user_text: str) -> bool:
        has_invite_ctx = any(marker in user_text for marker in ("초대", "invitation"))
        has_list_marker = any(marker in user_text for marker in ("목록", "리스트", "보여", "조회", "현황"))
        return has_invite_ctx and has_list_marker

    def _is_member_list_request(self, user_text: str) -> bool:
        return "멤버" in user_text and any(marker in user_text for marker in ("목록", "리스트", "보여", "조회"))

    def _is_member_add_request(self, user_text: str) -> bool:
        has_member_ctx = "멤버" in user_text or "구성원" in user_text
        has_add_marker = any(marker in user_text for marker in ("추가", "넣어", "초대"))
        # "user1 추가하고 user2도 추가" 처럼 멤버 키워드 없이 여러 사람을 추가하는 패턴
        has_multi_add = has_add_marker and any(marker in user_text for marker in ("하고", "도 추가", "도추가"))
        return has_add_marker and (has_member_ctx or has_multi_add)

    def _is_member_remove_request(self, user_text: str) -> bool:
        has_member_ctx = "멤버" in user_text or "구성원" in user_text
        has_remove_marker = any(marker in user_text for marker in ("제거", "삭제", "지워", "빼", "강퇴", "퇴출"))
        # "강퇴" 같은 동사 자체가 멤버 제거를 의미하므로 멤버 키워드 없어도 인정
        is_kick_verb = any(marker in user_text for marker in ("강퇴", "퇴출"))
        return has_remove_marker and (has_member_ctx or is_kick_verb)

    def _is_transfer_ownership_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in lowered for marker in ("소유권", "owner", "ownership")) and any(
            marker in lowered for marker in ("넘겨", "이전", "transfer")
        )

    def _is_resource_limit_request(self, user_text: str) -> bool:
        return self._has_project_context(user_text) and "리소스" in user_text and any(
            marker in user_text for marker in ("한도", "제한")
        )

    def _is_owner_check_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return self._has_project_context(user_text) and any(marker in lowered for marker in ("owner", "소유자"))

    def _is_project_list_request(self, user_text: str) -> bool:
        return (
            self._has_project_context(user_text)
            and any(marker in user_text for marker in ("목록", "리스트"))
            and not self._is_member_list_request(user_text)
            and not self._has_application_context(user_text)
        )

    def _is_available_check_request(self, user_text: str) -> bool:
        return self._has_project_context(user_text) and any(
            marker in user_text for marker in ("접근 가능", "사용 가능", "가능한지", "가능해")
        )

    def _is_project_detail_request(self, user_text: str) -> bool:
        return (
            self._has_project_context(user_text)
            and any(marker in user_text for marker in ("상세", "자세히", "정보"))
            and not self._has_application_context(user_text)
        )

    def _is_app_list_request(self, user_text: str) -> bool:
        return self._has_project_context(user_text) and self._has_application_context(user_text) and any(
            marker in user_text for marker in ("목록", "리스트", "보여", "조회")
        )

    def _is_app_status_request(self, user_text: str) -> bool:
        return self._has_application_context(user_text) and "상태" in user_text

    def _is_app_logs_request(self, user_text: str) -> bool:
        return self._has_application_context(user_text) and "로그" in user_text

    def _is_app_details_request(self, user_text: str) -> bool:
        return self._has_application_context(user_text) and any(
            marker in user_text for marker in ("상세", "자세히", "정보")
        )

    @staticmethod
    def _has_project_context(user_text: str) -> bool:
        return "프로젝트" in user_text

    @staticmethod
    def _has_application_context(user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in user_text for marker in ("앱", "애플리케이션", "어플리케이션")) or any(
            marker in lowered for marker in ("app", "application")
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
