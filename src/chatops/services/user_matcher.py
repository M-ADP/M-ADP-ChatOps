from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chatops.services.name_matcher import match_name


@dataclass(frozen=True)
class UserMatchResult:
    entry: dict[str, Any] | None
    matched_alias: str | None
    match_type: str | None
    auto_corrected: bool
    suggestions: list[str]

    @property
    def user_id(self) -> int | None:
        if not isinstance(self.entry, dict):
            return None
        return _coerce_optional_int(
            self.entry.get("resolved_id") or self.entry.get("user_id") or self.entry.get("id")
        )

    @property
    def canonical_name(self) -> str | None:
        if not isinstance(self.entry, dict):
            return None
        return _display_name(self.entry)


def match_user(query: str, entries: list[dict[str, Any]] | Any, *, project_name: str | None = None) -> UserMatchResult:
    if not isinstance(entries, list) or not isinstance(query, str) or not query.strip():
        return UserMatchResult(entry=None, matched_alias=None, match_type=None, auto_corrected=False, suggestions=[])

    alias_to_entry: dict[str, dict[str, Any]] = {}
    aliases: list[str] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry_project_name = raw_entry.get("project_name")
        if project_name is not None and entry_project_name not in (None, project_name):
            continue
        entry_aliases = _entry_aliases(raw_entry)
        if not entry_aliases:
            continue
        for alias in entry_aliases:
            if alias in alias_to_entry:
                continue
            alias_to_entry[alias] = raw_entry
            aliases.append(alias)

    matched = match_name(query, aliases)
    if matched.matched_name is not None:
        return UserMatchResult(
            entry=alias_to_entry.get(matched.matched_name),
            matched_alias=matched.matched_name,
            match_type=matched.match_type,
            auto_corrected=matched.auto_corrected,
            suggestions=_display_suggestions(matched.suggestions, alias_to_entry),
        )
    return UserMatchResult(
        entry=None,
        matched_alias=None,
        match_type=None,
        auto_corrected=False,
        suggestions=_display_suggestions(matched.suggestions, alias_to_entry),
    )


def _entry_aliases(entry: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for value in (
        entry.get("canonical_name"),
        entry.get("nickname"),
        entry.get("username"),
    ):
        _append_alias(aliases, value)
    raw_aliases = entry.get("aliases")
    if isinstance(raw_aliases, list):
        for value in raw_aliases:
            _append_alias(aliases, value)
    return aliases


def _append_alias(target: list[str], value: Any) -> None:
    if value is None:
        return
    alias = str(value).strip()
    if not alias or alias in target:
        return
    target.append(alias)


def _display_name(entry: dict[str, Any]) -> str | None:
    for value in (entry.get("nickname"), entry.get("canonical_name"), entry.get("username")):
        if value is None:
            continue
        name = str(value).strip()
        if name:
            return name
    return None


def _display_suggestions(
    alias_suggestions: list[str],
    alias_to_entry: dict[str, dict[str, Any]],
) -> list[str]:
    suggestions: list[str] = []
    for alias in alias_suggestions:
        entry = alias_to_entry.get(alias)
        display_name = _display_name(entry) if isinstance(entry, dict) else None
        value = display_name or alias
        if value not in suggestions:
            suggestions.append(value)
    return suggestions


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
