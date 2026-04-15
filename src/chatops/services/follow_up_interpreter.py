from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


CHOICE_NUMBER_PATTERN = re.compile(r"^(?P<value>\d+)(?:번)?$")
CHOICE_LETTER_PATTERN = re.compile(r"^(?P<value>[a-z])$", re.IGNORECASE)


@dataclass(frozen=True)
class FollowUpRewrite:
    kind: str
    message_text: str


class FollowUpInterpreterService:
    def rewrite(
        self,
        *,
        message_text: str,
        previous_request_status: str | None,
        session_context: dict[str, Any] | None,
    ) -> FollowUpRewrite | None:
        if not isinstance(message_text, str) or not message_text.strip():
            return None
        if not isinstance(session_context, dict):
            return None

        task_snapshot = session_context.get("last_task_snapshot")
        if not isinstance(task_snapshot, dict):
            return None
        follow_up_prompt = task_snapshot.get("follow_up_prompt")
        if not isinstance(follow_up_prompt, dict):
            return None

        prompt_kind = str(follow_up_prompt.get("kind") or "")
        if previous_request_status == "ambiguous" and prompt_kind == "choice":
            return self._rewrite_choice(message_text=message_text, session_context=session_context, prompt=follow_up_prompt)
        if previous_request_status == "input_required" and prompt_kind == "missing_input":
            return self._rewrite_missing_input(message_text=message_text, prompt=follow_up_prompt)
        return None

    def _rewrite_choice(
        self,
        *,
        message_text: str,
        session_context: dict[str, Any],
        prompt: dict[str, Any],
    ) -> FollowUpRewrite | None:
        options = prompt.get("options")
        if not isinstance(options, list) or not options:
            return None

        selected_value = self._match_choice_value(message_text=message_text, options=options)
        if selected_value is None:
            return None

        base_message = session_context.get("last_effective_message_text") or session_context.get("last_message_text")
        if not isinstance(base_message, str) or not base_message.strip():
            return None

        return FollowUpRewrite(
            kind="ambiguity_choice",
            message_text=f"{base_message}\n{selected_value}".strip(),
        )

    def _match_choice_value(self, *, message_text: str, options: list[dict[str, Any]]) -> str | None:
        normalized = message_text.strip()
        collapsed = self._collapse_text(normalized)

        number_match = CHOICE_NUMBER_PATTERN.fullmatch(normalized)
        if number_match:
            index = int(number_match.group("value")) - 1
            if 0 <= index < len(options):
                return self._option_value(options[index])

        letter_match = CHOICE_LETTER_PATTERN.fullmatch(normalized)
        if letter_match:
            index = ord(letter_match.group("value").lower()) - ord("a")
            if 0 <= index < len(options):
                return self._option_value(options[index])

        for option in options:
            label = str(option.get("label") or "").strip()
            value = self._option_value(option)
            if normalized == label or normalized == value:
                return value

        for option in options:
            label = str(option.get("label") or "").strip()
            value = self._option_value(option)
            label_collapsed = self._collapse_text(label)
            value_collapsed = self._collapse_text(value)
            if not label_collapsed and not value_collapsed:
                continue
            if collapsed and (
                collapsed in label_collapsed
                or label_collapsed in collapsed
                or collapsed in value_collapsed
                or value_collapsed in collapsed
            ):
                return value
        return None

    def _rewrite_missing_input(
        self,
        *,
        message_text: str,
        prompt: dict[str, Any],
    ) -> FollowUpRewrite | None:
        fields = prompt.get("fields")
        if not isinstance(fields, list) or not fields:
            return None

        normalized = message_text.strip()
        if len(fields) == 1:
            key = str(fields[0].get("key") or "").strip()
            if not key:
                return None
            return FollowUpRewrite(kind="missing_input_fill", message_text=f"{key}={normalized}")

        parts = [part.strip() for part in normalized.split(",")]
        if len(parts) != len(fields) or any(not part for part in parts):
            return None

        assignments = []
        for field, value in zip(fields, parts):
            key = str(field.get("key") or "").strip()
            if not key:
                return None
            assignments.append(f"{key}={value}")
        return FollowUpRewrite(kind="missing_input_fill", message_text=" ".join(assignments))

    @staticmethod
    def _option_value(option: dict[str, Any]) -> str:
        return str(option.get("value") or option.get("label") or "").strip()

    @staticmethod
    def _collapse_text(value: str) -> str:
        return "".join(value.lower().split())
