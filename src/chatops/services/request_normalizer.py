from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestNormalizerService:
    _TRAILING_NOISE_PATTERN = re.compile(r"[?!~]+$|[ㅡ]+$")
    _WHITESPACE_PATTERN = re.compile(r"\s+")
    _REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"어플리케이션"), "앱"),
        (re.compile(r"애플리케이션"), "앱"),
        (re.compile(r"어플"), "앱"),
        (re.compile(r"프젝"), "프로젝트"),
    )

    def normalize(self, message_text: str) -> str:
        if not isinstance(message_text, str):
            return ""

        if not message_text.strip():
            return ""

        normalized_lines: list[str] = []
        for raw_line in message_text.splitlines():
            normalized = raw_line.strip()
            if not normalized:
                continue

            for pattern, replacement in self._REPLACEMENTS:
                normalized = pattern.sub(replacement, normalized)

            normalized = self._TRAILING_NOISE_PATTERN.sub("", normalized).strip()
            normalized = self._WHITESPACE_PATTERN.sub(" ", normalized).strip()
            if normalized:
                normalized_lines.append(normalized)

        return "\n".join(normalized_lines)
