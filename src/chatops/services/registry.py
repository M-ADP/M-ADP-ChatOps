from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import yaml


TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9_./-]+")
KEY_VALUE_PATTERN = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?P<value>[^\s,}]+)")
JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
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
    "update": {"update", "수정", "변경", "업데이트"},
    "member": {"member", "멤버", "구성원"},
    "members": {"member", "members", "멤버", "구성원"},
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
    required_inputs: dict[str, Any]
    preconditions: tuple[str, ...]
    missing_info_questions: tuple[str, ...]
    response_interpretation: str
    plan_template: tuple[str, ...]
    examples: tuple[str, ...]

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
            side_effects=tuple(data.get("side_effects", [])),
            required_headers=tuple(data.get("required_headers", [])),
            required_inputs=data.get("required_inputs", {}),
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
        return len(overlap) + (len(id_overlap) * 3) + (len(capability_overlap) * 2) + required_input_score

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
        if not json_match:
            return supplied_fields

        try:
            loaded = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return supplied_fields

        if isinstance(loaded, dict):
            supplied_fields.update(str(key) for key in loaded.keys())
        return supplied_fields

    def _score_required_inputs(self, entry: RegistryEntry, supplied_fields: set[str]) -> int:
        score = 0
        required_inputs = entry.required_inputs
        required_field_names: set[str] = set()

        for field in required_inputs.get("path", []):
            field_name = str(field.get("name", ""))
            if field_name:
                required_field_names.add(field_name)
            if field_name in supplied_fields:
                score += 2
        for field in required_inputs.get("query", []):
            if not field.get("required", False):
                continue
            field_name = str(field.get("name", ""))
            if field_name:
                required_field_names.add(field_name)
            if field_name in supplied_fields:
                score += 2

        body_spec = required_inputs.get("body")
        if isinstance(body_spec, dict):
            for field_name in body_spec.get("required_fields", []):
                normalized = str(field_name)
                required_field_names.add(normalized)
                if normalized in supplied_fields:
                    score += 2

        if not required_field_names:
            return score + 2

        missing_required = required_field_names - supplied_fields
        score -= len(missing_required) * 2
        return score
