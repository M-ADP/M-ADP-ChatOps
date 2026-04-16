from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from chatops.services.name_matcher import normalize_name


@dataclass(frozen=True)
class EasterEggService:
    responses: Mapping[str, str] = field(default_factory=dict)

    def match_names(self, message_text: str | None) -> list[str]:
        if not isinstance(message_text, str) or not message_text.strip():
            return []
        normalized_text = normalize_name(message_text)
        if not normalized_text:
            return []
        matched_names: list[str] = []
        for name in self.responses:
            normalized_name = normalize_name(name)
            if normalized_name and normalized_name in normalized_text:
                matched_names.append(name)
        return matched_names

    def decorate_response(self, message_text: str | None, response_text: str | None) -> str | None:
        if not isinstance(response_text, str) or not response_text.strip():
            return response_text
        matched_messages = [
            self.responses[name].strip()
            for name in self.match_names(message_text)
            if isinstance(self.responses.get(name), str) and self.responses[name].strip()
        ]
        if not matched_messages:
            return response_text
        return f"{response_text.rstrip()}\n\n" + "\n".join(matched_messages)
